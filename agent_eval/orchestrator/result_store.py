"""Result storage backends."""

import json
import os
from typing import Any, Dict, List, Optional


class ResultStore:
    """Abstract result store."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.backend_type = self.config.get("type", "json")
        self._backend = self._create_backend()

    def _create_backend(self):
        if self.backend_type == "json":
            return JSONBackend(self.config.get("output_dir", "./eval_results"))
        elif self.backend_type == "sqlite":
            return SQLiteBackend(self.config.get("path", "./eval_results/results.db"))
        elif self.backend_type == "memory":
            return MemoryBackend()
        else:
            raise ValueError(f"Unknown storage type: {self.backend_type}")

    def save(self, report: "EvaluationReport") -> str:
        return self._backend.save(report)

    def load(self, report_id: str) -> Optional["EvaluationReport"]:
        return self._backend.load(report_id)

    def list_reports(self) -> List[Dict[str, Any]]:
        return self._backend.list_reports()

    def delete(self, report_id: str) -> bool:
        return self._backend.delete(report_id)

    def compare(self, report_ids: List[str]) -> Dict[str, Any]:
        reports = []
        for rid in report_ids:
            r = self.load(rid)
            if r:
                reports.append(r)
        return {"comparison": self._compare_reports(reports), "reports": reports}

    def _compare_reports(self, reports: List["EvaluationReport"]) -> Dict[str, Any]:
        if len(reports) < 2:
            return {}
        result = {}
        names = [r.metadata.get("agent_name", f"report_{i}") for i, r in enumerate(reports)]
        for dim in reports[0].summary.get("dimensions", {}):
            scores = [r.summary.get("dimensions", {}).get(dim, 0) for r in reports]
            result[dim] = dict(zip(names, scores))
        return result


class JSONBackend:
    """JSON file-based storage."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def save(self, report: "EvaluationReport") -> str:
        filepath = os.path.join(self.output_dir, f"{report.run_id}.json")
        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        return filepath

    def load(self, report_id: str) -> Optional["EvaluationReport"]:
        filepath = os.path.join(self.output_dir, f"{report_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath) as f:
            data = json.load(f)
            return EvaluationReport.from_dict(data)

    def list_reports(self) -> List[Dict[str, Any]]:
        reports = []
        for fname in sorted(os.listdir(self.output_dir), reverse=True):
            if fname.endswith(".json"):
                filepath = os.path.join(self.output_dir, fname)
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                        reports.append({
                            "run_id": data.get("run_id"),
                            "timestamp": data.get("timestamp"),
                            "agent_name": data.get("metadata", {}).get("agent_name", ""),
                            "overall_score": data.get("summary", {}).get("overall_score"),
                        })
                except Exception:
                    pass
        return reports

    def delete(self, report_id: str) -> bool:
        filepath = os.path.join(self.output_dir, f"{report_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False


class SQLiteBackend:
    """SQLite-based storage."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        import sqlite3
        conn = sqlite3.connect(self.path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT,
                data TEXT
            )
        """)
        conn.commit()
        conn.close()

    def save(self, report: "EvaluationReport") -> str:
        import sqlite3
        conn = sqlite3.connect(self.path)
        conn.execute(
            "INSERT OR REPLACE INTO reports (run_id, timestamp, data) VALUES (?, ?, ?)",
            (report.run_id, report.timestamp, json.dumps(report.to_dict())),
        )
        conn.commit()
        conn.close()
        return report.run_id

    def load(self, report_id: str) -> Optional["EvaluationReport"]:
        import sqlite3
        conn = sqlite3.connect(self.path)
        cursor = conn.execute("SELECT data FROM reports WHERE run_id = ?", (report_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return EvaluationReport.from_dict(json.loads(row[0]))
        return None

    def list_reports(self) -> List[Dict[str, Any]]:
        import sqlite3
        conn = sqlite3.connect(self.path)
        cursor = conn.execute("SELECT run_id, timestamp, data FROM reports ORDER BY timestamp DESC")
        reports = []
        for row in cursor:
            data = json.loads(row[2])
            reports.append({
                "run_id": row[0],
                "timestamp": row[1],
                "agent_name": data.get("metadata", {}).get("agent_name", ""),
                "overall_score": data.get("summary", {}).get("overall_score"),
            })
        conn.close()
        return reports

    def delete(self, report_id: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(self.path)
        cursor = conn.execute("DELETE FROM reports WHERE run_id = ?", (report_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted


class MemoryBackend:
    """In-memory storage (for testing)."""

    def __init__(self):
        self._store: Dict[str, "EvaluationReport"] = {}

    def save(self, report: "EvaluationReport") -> str:
        self._store[report.run_id] = report
        return report.run_id

    def load(self, report_id: str) -> Optional["EvaluationReport"]:
        return self._store.get(report_id)

    def list_reports(self) -> List[Dict[str, Any]]:
        return [
            {
                "run_id": r.run_id,
                "timestamp": r.timestamp,
                "agent_name": r.metadata.get("agent_name", ""),
                "overall_score": r.summary.get("overall_score"),
            }
            for r in sorted(self._store.values(), key=lambda x: x.timestamp, reverse=True)
        ]

    def delete(self, report_id: str) -> bool:
        if report_id in self._store:
            del self._store[report_id]
            return True
        return False


class EvaluationReport:
    """Structured evaluation report."""

    def __init__(
        self,
        run_id: str,
        timestamp: str,
        agent_name: str,
        agent_version: str,
        summary: Dict[str, Any],
        plugin_results: Dict[str, Any],
        metadata: Dict[str, Any],
        artifacts: List[Any] = None,
    ):
        self.run_id = run_id
        self.timestamp = timestamp
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.summary = summary
        self.plugin_results = plugin_results
        self.metadata = metadata
        self.artifacts = artifacts or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "agent": {"name": self.agent_name, "version": self.agent_version},
            "summary": self.summary,
            "plugin_results": self.plugin_results,
            "metadata": self.metadata,
            "artifacts_count": len(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationReport":
        agent = data.get("agent", {})
        return cls(
            run_id=data["run_id"],
            timestamp=data["timestamp"],
            agent_name=agent.get("name", "unknown"),
            agent_version=agent.get("version", "1.0"),
            summary=data["summary"],
            plugin_results=data["plugin_results"],
            metadata=data.get("metadata", {}),
        )