"""Persistent storage for trace records. Supports JSON files, SQLite, and memory."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from agent_eval.trace.schema import TraceRecord


class TraceStore:
    """Persistent storage for TraceRecords.

    Backends:
      - "json": one file per trace in a directory
      - "sqlite": single SQLite database
      - "memory": in-process dict (for testing)
    """

    def __init__(self, backend: str = "json", path: str = "./traces"):
        self.backend = backend
        self.path = path
        self._lock = threading.Lock()
        self._mem: Dict[str, TraceRecord] = {}

        if backend == "json":
            os.makedirs(path, exist_ok=True)
        elif backend == "sqlite":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._init_sqlite()
        elif backend != "memory":
            raise ValueError(f"Unknown backend: {backend}. Use json, sqlite, or memory.")

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                timestamp TEXT,
                agent_name TEXT,
                trace_type TEXT,
                success INTEGER,
                quality_score REAL,
                duration_ms INTEGER,
                tags TEXT,
                data TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent ON traces(agent_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON traces(trace_type)
        """)
        conn.commit()
        self._sqlite_conn = conn

    def save(self, record: TraceRecord) -> str:
        """Save a single trace record."""
        with self._lock:
            if self.backend == "memory":
                self._mem[record.trace_id] = record
            elif self.backend == "json":
                fpath = os.path.join(self.path, f"{record.trace_id}.json")
                with open(fpath, "w") as f:
                    json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
            elif self.backend == "sqlite":
                d = record.to_dict()
                self._sqlite_conn.execute(
                    "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        record.trace_id,
                        record.timestamp,
                        record.agent_name,
                        record.trace_type,
                        int(record.success),
                        record.quality_score,
                        record.duration_ms,
                        json.dumps(record.tags),
                        json.dumps(d),
                    ),
                )
                self._sqlite_conn.commit()
        return record.trace_id

    def save_batch(self, records: List[TraceRecord]) -> List[str]:
        """Save multiple traces."""
        return [self.save(r) for r in records]

    def load(self, trace_id: str) -> Optional[TraceRecord]:
        """Load a trace by ID."""
        with self._lock:
            if self.backend == "memory":
                return self._mem.get(trace_id)
            elif self.backend == "json":
                fpath = os.path.join(self.path, f"{trace_id}.json")
                if not os.path.exists(fpath):
                    return None
                with open(fpath) as f:
                    return TraceRecord.from_dict(json.load(f))
            elif self.backend == "sqlite":
                row = self._sqlite_conn.execute(
                    "SELECT data FROM traces WHERE trace_id=?", (trace_id,)
                ).fetchone()
                if row:
                    return TraceRecord.from_dict(json.loads(row[0]))
                return None

    def query(self, filters: Optional[Dict[str, Any]] = None) -> List[TraceRecord]:
        """Query traces by filters.

        Supported filters:
          agent_name, trace_type, success, source, tags,
          min_quality, min_duration, max_duration, limit
        """
        filters = filters or {}
        limit = filters.pop("limit", 0)

        with self._lock:
            records = self._load_all()

        results: List[TraceRecord] = []
        for r in records:
            match = True
            for key, val in filters.items():
                if key == "agent_name" and r.agent_name != val:
                    match = False
                elif key == "trace_type" and r.trace_type != val:
                    match = False
                elif key == "success" and r.success != val:
                    match = False
                elif key == "source" and r.source != val:
                    match = False
                elif key == "min_quality" and r.quality_score < val:
                    match = False
                elif key == "min_duration" and r.duration_ms < val:
                    match = False
                elif key == "max_duration" and r.duration_ms > val:
                    match = False
                elif key == "tags":
                    if isinstance(val, str):
                        val = [val]
                    if not any(t in r.tags for t in val):
                        match = False
            if match:
                results.append(r)

        if limit > 0:
            results = results[:limit]
        return results

    def _load_all(self) -> List[TraceRecord]:
        if self.backend == "memory":
            return list(self._mem.values())
        elif self.backend == "json":
            records: List[TraceRecord] = []
            if os.path.isdir(self.path):
                for fname in os.listdir(self.path):
                    if fname.endswith(".json"):
                        try:
                            with open(os.path.join(self.path, fname)) as f:
                                records.append(TraceRecord.from_dict(json.load(f)))
                        except (json.JSONDecodeError, KeyError):
                            continue
            return records
        elif self.backend == "sqlite":
            rows = self._sqlite_conn.execute("SELECT data FROM traces").fetchall()
            return [TraceRecord.from_dict(json.loads(r[0])) for r in rows]
        return []

    def count(self, filters: Optional[Dict] = None) -> int:
        return len(self.query(filters))

    def delete(self, trace_id: str) -> bool:
        with self._lock:
            if self.backend == "memory":
                return self._mem.pop(trace_id, None) is not None
            elif self.backend == "json":
                fpath = os.path.join(self.path, f"{trace_id}.json")
                if os.path.exists(fpath):
                    os.remove(fpath)
                    return True
                return False
            elif self.backend == "sqlite":
                cur = self._sqlite_conn.execute("DELETE FROM traces WHERE trace_id=?", (trace_id,))
                self._sqlite_conn.commit()
                return cur.rowcount > 0
        return False

    def clear(self) -> int:
        """Clear all traces. Returns count deleted."""
        count = self.count()
        with self._lock:
            if self.backend == "memory":
                self._mem.clear()
            elif self.backend == "json":
                for fname in os.listdir(self.path):
                    if fname.endswith(".json"):
                        os.remove(os.path.join(self.path, fname))
            elif self.backend == "sqlite":
                self._sqlite_conn.execute("DELETE FROM traces")
                self._sqlite_conn.commit()
        return count

    def import_dir(self, dir_path: str, source: str = "custom") -> int:
        """Import trace JSON files from a directory."""
        count = 0
        for fname in os.listdir(dir_path):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(dir_path, fname)) as f:
                    raw = json.load(f)
                record = TraceRecord.from_dict(raw)
                record.source = source
                self.save(record)
                count += 1
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return count

    def stats(self) -> Dict[str, Any]:
        """Get aggregate statistics."""
        records = self._load_all()
        if not records:
            return {"total": 0}

        by_type: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        durations: List[int] = []
        qualities: List[float] = []

        for r in records:
            by_type[r.trace_type] = by_type.get(r.trace_type, 0) + 1
            by_agent[r.agent_name] = by_agent.get(r.agent_name, 0) + 1
            durations.append(r.duration_ms)
            qualities.append(r.quality_score)

        return {
            "total": len(records),
            "by_type": by_type,
            "by_agent": by_agent,
            "success_rate": sum(1 for r in records if r.success) / len(records),
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "avg_quality": sum(qualities) / len(qualities) if qualities else 0,
            "avg_tool_calls": sum(r.num_tool_calls for r in records) / len(records),
            "avg_turns": sum(r.num_turns for r in records) / len(records),
        }
