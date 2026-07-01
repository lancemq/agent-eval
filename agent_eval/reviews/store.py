"""Persistent, versioned human review store.

A review session is a named, versioned collection of review items. Each item
references a trace or run output and holds a reviewer's verdict (pending /
approved / rejected / changes_requested), notes, and labels. Sessions are
persisted as one JSON file per session under
``{workspace}/.agent-eval/reviews/{name}.json``.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")

_REVIEW_STATUSES = {"pending", "approved", "rejected", "changes_requested"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class ReviewItem:
    """A single reviewable output within a session."""

    item_id: str = field(default_factory=_gen_id)
    trace_id: str = ""
    run_id: str = ""
    task_id: str = ""
    output: str = ""
    expected: str = ""
    reviewer: str = ""
    status: str = "pending"
    labels: List[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "output": self.output,
            "expected": self.expected,
            "reviewer": self.reviewer,
            "status": self.status,
            "labels": self.labels,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReviewItem":
        return cls(
            item_id=d.get("item_id", _gen_id()),
            trace_id=d.get("trace_id", ""),
            run_id=d.get("run_id", ""),
            task_id=d.get("task_id", ""),
            output=d.get("output", ""),
            expected=d.get("expected", ""),
            reviewer=d.get("reviewer", ""),
            status=d.get("status", "pending"),
            labels=d.get("labels", []),
            notes=d.get("notes", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class ReviewSession:
    """A versioned snapshot of a review session."""

    name: str
    version: str
    description: str = ""
    items: List[ReviewItem] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReviewSession":
        return cls(
            name=d["name"],
            version=d.get("version", "1"),
            description=d.get("description", ""),
            items=[ReviewItem.from_dict(i) for i in d.get("items", [])],
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            metadata=d.get("metadata", {}),
        )

    @property
    def item_count(self) -> int:
        return len(self.items)


def _bump_version(current: str, kind: str = "patch") -> str:
    parts = current.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = (int(p) for p in parts)
        if kind == "major":
            return f"{major + 1}.0.0"
        if kind == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"
    m = re.match(r"^(.*?)(\d+)$", current)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    return f"{current}.1"


class ReviewStore:
    """Persistent store for versioned review sessions.

    One JSON file per session under ``{workspace}/.agent-eval/reviews/``.
    Each file: ``{"name": ..., "versions": [ReviewSession, ...]}``.
    """

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace or os.getcwd())
        self.dir = os.path.join(self.workspace, ".agent-eval", "reviews")
        self._lock = threading.RLock()
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, name: str) -> str:
        self._validate_name(name)
        return os.path.join(self.dir, f"{name}.json")

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not _NAME_PATTERN.match(name):
            raise ValueError(
                f"invalid review name: {name!r} (use letters, digits, '_', '-', '.', "
                "and start with a letter/digit/underscore)"
            )

    @staticmethod
    def _validate_status(status: str) -> None:
        if status and status not in _REVIEW_STATUSES:
            raise ValueError(f"invalid status: {status!r} (expected one of {sorted(_REVIEW_STATUSES)})")

    def _read(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(f"review session not found: {name}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name: str, data: Dict[str, Any]) -> None:
        path = self._path(name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def list_sessions(self) -> List[Dict[str, Any]]:
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
                items = latest.get("items", [])
                pending = sum(1 for it in items if it.get("status") == "pending")
                out.append({
                    "name": name,
                    "latest_version": latest.get("version"),
                    "version_count": len(versions),
                    "item_count": len(items),
                    "pending_count": pending,
                    "description": latest.get("description", ""),
                    "updated_at": latest.get("updated_at", ""),
                    "created_at": versions[0].get("created_at", ""),
                })
            return out

    def get(self, name: str, version: Optional[str] = None) -> ReviewSession:
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"review {name!r} has no versions")
            if version is None:
                return ReviewSession.from_dict(versions[-1])
            for v in versions:
                if v.get("version") == version:
                    return ReviewSession.from_dict(v)
            raise KeyError(f"review {name!r} has no version {version!r}")

    def list_versions(self, name: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(name)
            return [
                {
                    "version": v.get("version"),
                    "item_count": len(v.get("items", [])),
                    "created_at": v.get("created_at", ""),
                    "updated_at": v.get("updated_at", ""),
                    "description": v.get("description", ""),
                }
                for v in data.get("versions", [])
            ]

    def create(
        self,
        name: str,
        items: List[Dict[str, Any]],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
    ) -> ReviewSession:
        with self._lock:
            path = self._path(name)
            if os.path.exists(path):
                raise ValueError(f"review session already exists: {name}")
            now = _now()
            record = ReviewSession(
                name=name,
                version=version,
                description=description,
                items=[ReviewItem.from_dict(i) for i in items],
                created_at=now,
                updated_at=now,
                metadata=dict(metadata or {}),
            )
            self._write(name, {"name": name, "versions": [record.to_dict()]})
            return record

    def add_items(
        self,
        name: str,
        items: List[Dict[str, Any]],
    ) -> ReviewSession:
        """Append items to the latest version (creates a new patch version)."""
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"review {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "patch")
            now = _now()
            existing_items = [ReviewItem.from_dict(i) for i in prev.get("items", [])]
            new_items = [ReviewItem.from_dict(i) for i in items]
            all_items = existing_items + new_items
            record = ReviewSession(
                name=name,
                version=new_version,
                description=prev.get("description", ""),
                items=all_items,
                created_at=prev.get("created_at", now),
                updated_at=now,
                metadata=prev.get("metadata", {}),
            )
            versions.append(record.to_dict())
            data["versions"] = versions
            self._write(name, data)
            return record

    def update_item(
        self,
        name: str,
        item_id: str,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        labels: Optional[List[str]] = None,
        reviewer: Optional[str] = None,
    ) -> ReviewSession:
        """Update a single item's review verdict (creates a new patch version)."""
        self._validate_status(status or "")
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"review {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "patch")
            now = _now()
            items = [ReviewItem.from_dict(i) for i in prev.get("items", [])]
            found = False
            for item in items:
                if item.item_id == item_id:
                    if status is not None:
                        item.status = status
                    if notes is not None:
                        item.notes = notes
                    if labels is not None:
                        item.labels = labels
                    if reviewer is not None:
                        item.reviewer = reviewer
                    item.updated_at = now
                    found = True
                    break
            if not found:
                raise KeyError(f"item {item_id!r} not found in review {name!r}")
            record = ReviewSession(
                name=name,
                version=new_version,
                description=prev.get("description", ""),
                items=items,
                created_at=prev.get("created_at", now),
                updated_at=now,
                metadata=prev.get("metadata", {}),
            )
            versions.append(record.to_dict())
            data["versions"] = versions
            self._write(name, data)
            return record

    def delete(self, name: str) -> bool:
        with self._lock:
            path = self._path(name)
            if os.path.exists(path):
                os.remove(path)
                return True
            return False
