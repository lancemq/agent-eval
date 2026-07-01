"""Persistent, versioned dataset store.

A dataset is a named, versioned collection of test-case rows. Each row is a
free-schema dict (typically containing ``task_id``, ``input``, ``expected``).
Datasets are persisted as one JSON file per dataset under
``{workspace}/.agent-eval/datasets/{name}.json``. Each file holds the full
version history chain so any prior version can be loaded and diffed.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(value: Any) -> str:
    """Canonical JSON string for equality comparison (sorted keys)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _row_key(row: Dict[str, Any]) -> str:
    """Stable identity for a row: explicit task_id, else hash of normalized row."""
    task_id = row.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    return "hash:" + _normalize(row)[:32]


@dataclass
class DatasetRecord:
    """A single versioned snapshot of a dataset."""

    name: str
    version: str
    description: str = ""
    rows: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    source_traces: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "rows": self.rows,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_traces": self.source_traces,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetRecord":
        return cls(
            name=d["name"],
            version=d.get("version", "1"),
            description=d.get("description", ""),
            rows=d.get("rows", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            source_traces=d.get("source_traces", []),
            metadata=d.get("metadata", {}),
        )

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _bump_version(current: str, kind: str = "patch") -> str:
    """Bump a semver-like version string. Supports ``major.minor.patch``.

    ``add_version`` -> minor bump; ``update_rows`` -> patch bump.
    Falls back to incrementing a trailing integer for non-semver versions.
    """
    parts = current.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = (int(p) for p in parts)
        if kind == "major":
            return f"{major + 1}.0.0"
        if kind == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"
    # Fallback: try to bump trailing integer
    m = re.match(r"^(.*?)(\d+)$", current)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    return f"{current}.1"


class DatasetStore:
    """Persistent store for versioned datasets.

    One JSON file per dataset under ``{workspace}/.agent-eval/datasets/``.
    Each file: ``{"name": ..., "versions": [DatasetRecord, ...]}``.
    """

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace or os.getcwd())
        self.dir = os.path.join(self.workspace, ".agent-eval", "datasets")
        self._lock = threading.RLock()
        os.makedirs(self.dir, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def _path(self, name: str) -> str:
        self._validate_name(name)
        return os.path.join(self.dir, f"{name}.json")

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not _NAME_PATTERN.match(name):
            raise ValueError(
                f"invalid dataset name: {name!r} (use letters, digits, '_', '-', '.', "
                "and start with a letter/digit/underscore)"
            )

    # ----------------------------------------------------------------- io
    def _read(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(f"dataset not found: {name}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name: str, data: Dict[str, Any]) -> None:
        path = self._path(name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    # --------------------------------------------------------------- list
    def list_datasets(self) -> List[Dict[str, Any]]:
        """Return summary for every dataset (latest version highlighted)."""
        with self._lock:
            out: List[Dict[str, Any]] = []
            for fname in sorted(os.listdir(self.dir)):
                if not fname.endswith(".json"):
                    continue
                name = fname[:-5]
                try:
                    data = self._read(name)
                except (KeyError, json.JSONDecodeError):
                    continue
                versions = data.get("versions", [])
                if not versions:
                    continue
                latest = versions[-1]
                out.append({
                    "name": name,
                    "latest_version": latest.get("version"),
                    "version_count": len(versions),
                    "row_count": len(latest.get("rows", [])),
                    "description": latest.get("description", ""),
                    "updated_at": latest.get("updated_at", ""),
                    "created_at": versions[0].get("created_at", ""),
                })
            return out

    # ---------------------------------------------------------------- get
    def get(self, name: str, version: Optional[str] = None) -> DatasetRecord:
        """Return a specific version (default: latest)."""
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"dataset {name!r} has no versions")
            if version is None:
                return DatasetRecord.from_dict(versions[-1])
            for v in versions:
                if v.get("version") == version:
                    return DatasetRecord.from_dict(v)
            raise KeyError(f"dataset {name!r} has no version {version!r}")

    def list_versions(self, name: str) -> List[Dict[str, Any]]:
        """Return lightweight metadata for all versions."""
        with self._lock:
            data = self._read(name)
            return [
                {
                    "version": v.get("version"),
                    "row_count": len(v.get("rows", [])),
                    "created_at": v.get("created_at", ""),
                    "updated_at": v.get("updated_at", ""),
                    "description": v.get("description", ""),
                    "source_traces": v.get("source_traces", []),
                }
                for v in data.get("versions", [])
            ]

    # ------------------------------------------------------------ create
    def create(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        description: str = "",
        source_traces: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
    ) -> DatasetRecord:
        """Create a new dataset with its first version."""
        with self._lock:
            path = self._path(name)
            if os.path.exists(path):
                raise ValueError(f"dataset already exists: {name}")
            now = _now()
            record = DatasetRecord(
                name=name,
                version=version,
                description=description,
                rows=list(rows),
                created_at=now,
                updated_at=now,
                source_traces=list(source_traces or []),
                metadata=dict(metadata or {}),
            )
            self._write(name, {"name": name, "versions": [record.to_dict()]})
            return record

    # -------------------------------------------------------- add version
    def add_version(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        description: Optional[str] = None,
        source_traces: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DatasetRecord:
        """Append a new minor version to an existing dataset."""
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"dataset {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "minor")
            now = _now()
            record = DatasetRecord(
                name=name,
                version=new_version,
                description=description if description is not None else prev.get("description", ""),
                rows=list(rows),
                created_at=now,
                updated_at=now,
                source_traces=list(source_traces or []),
                metadata={**prev.get("metadata", {}), **(metadata or {})},
            )
            versions.append(record.to_dict())
            data["versions"] = versions
            self._write(name, data)
            return record

    # --------------------------------------------------------- update rows
    def update_rows(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> DatasetRecord:
        """Update rows on the latest version in place (patch bump).

        Used by the online editor's "save" action. Creates a new patch
        version that replaces the latest rows so history is preserved.
        """
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"dataset {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "patch")
            now = _now()
            record = DatasetRecord(
                name=name,
                version=new_version,
                description=description if description is not None else prev.get("description", ""),
                rows=list(rows),
                created_at=prev.get("created_at", now),
                updated_at=now,
                source_traces=prev.get("source_traces", []),
                metadata=prev.get("metadata", {}),
            )
            versions.append(record.to_dict())
            data["versions"] = versions
            self._write(name, data)
            return record

    # -------------------------------------------------------------- delete
    def delete(self, name: str) -> bool:
        with self._lock:
            path = self._path(name)
            if os.path.exists(path):
                os.remove(path)
                return True
            return False

    def delete_version(self, name: str, version: str) -> bool:
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            new_versions = [v for v in versions if v.get("version") != version]
            if len(new_versions) == len(versions):
                return False
            if not new_versions:
                raise ValueError("cannot delete the only version; delete the dataset instead")
            data["versions"] = new_versions
            self._write(name, data)
            return True

    # ---------------------------------------------------------------- diff
    def diff(self, name: str, v1: str, v2: str) -> Dict[str, Any]:
        """Row-level diff between two versions, keyed by ``task_id``."""
        with self._lock:
            r1 = self.get(name, v1)
            r2 = self.get(name, v2)
        return diff_rows(r1.rows, r2.rows)


def diff_rows(rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute a row-level diff between two row lists.

    Aligns by ``task_id`` (falls back to a content hash for rows without one).
    Returns ``added``, ``removed``, ``modified`` (with per-field changes),
    plus ``summary`` counts.
    """
    a_map: Dict[str, Dict[str, Any]] = {}
    b_map: Dict[str, Dict[str, Any]] = {}
    for row in rows_a:
        a_map[_row_key(row)] = row
    for row in rows_b:
        b_map[_row_key(row)] = row

    a_keys = set(a_map)
    b_keys = set(b_map)

    added = [b_map[k] for k in sorted(b_keys - a_keys)]
    removed = [a_map[k] for k in sorted(a_keys - b_keys)]

    modified: List[Dict[str, Any]] = []
    for k in sorted(a_keys & b_keys):
        ra = a_map[k]
        rb = b_map[k]
        if _normalize(ra) == _normalize(rb):
            continue
        field_changes: Dict[str, Dict[str, Any]] = {}
        all_fields = set(ra) | set(rb)
        for fname in all_fields:
            va = ra.get(fname)
            vb = rb.get(fname)
            if _normalize(va) != _normalize(vb):
                field_changes[fname] = {"from": va, "to": vb}
        modified.append({
            "task_id": k,
            "fields": field_changes,
            "before": ra,
            "after": rb,
        })

    unchanged = len(a_keys & b_keys) - len(modified)
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": unchanged,
        },
    }
