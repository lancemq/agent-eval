"""Persistent, versioned prompt store.

A prompt is a named, versioned collection of chat messages (system + user
turns) plus optional model configuration. Prompts are persisted as one JSON
file per prompt under ``{workspace}/.agent-eval/prompts/{name}.json``. Each
file holds the full version history chain.
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
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


@dataclass
class PromptRecord:
    """A single versioned snapshot of a prompt."""

    name: str
    version: str
    description: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    model_config: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "messages": self.messages,
            "model_config": self.model_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PromptRecord":
        return cls(
            name=d["name"],
            version=d.get("version", "1"),
            description=d.get("description", ""),
            messages=d.get("messages", []),
            model_config=d.get("model_config", {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            metadata=d.get("metadata", {}),
        )


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


class PromptStore:
    """Persistent store for versioned prompts.

    One JSON file per prompt under ``{workspace}/.agent-eval/prompts/``.
    Each file: ``{"name": ..., "versions": [PromptRecord, ...]}``.
    """

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace or os.getcwd())
        self.dir = os.path.join(self.workspace, ".agent-eval", "prompts")
        self._lock = threading.RLock()
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, name: str) -> str:
        self._validate_name(name)
        return os.path.join(self.dir, f"{name}.json")

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not _NAME_PATTERN.match(name):
            raise ValueError(
                f"invalid prompt name: {name!r} (use letters, digits, '_', '-', '.', "
                "and start with a letter/digit/underscore)"
            )

    def _read(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(f"prompt not found: {name}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name: str, data: Dict[str, Any]) -> None:
        path = self._path(name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def list_prompts(self) -> List[Dict[str, Any]]:
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
                    "description": latest.get("description", ""),
                    "updated_at": latest.get("updated_at", ""),
                    "created_at": versions[0].get("created_at", ""),
                })
            return out

    def get(self, name: str, version: Optional[str] = None) -> PromptRecord:
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"prompt {name!r} has no versions")
            if version is None:
                return PromptRecord.from_dict(versions[-1])
            for v in versions:
                if v.get("version") == version:
                    return PromptRecord.from_dict(v)
            raise KeyError(f"prompt {name!r} has no version {version!r}")

    def list_versions(self, name: str) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(name)
            return [
                {
                    "version": v.get("version"),
                    "created_at": v.get("created_at", ""),
                    "updated_at": v.get("updated_at", ""),
                    "description": v.get("description", ""),
                }
                for v in data.get("versions", [])
            ]

    def create(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: str = "",
        model_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
    ) -> PromptRecord:
        with self._lock:
            path = self._path(name)
            if os.path.exists(path):
                raise ValueError(f"prompt already exists: {name}")
            now = _now()
            record = PromptRecord(
                name=name,
                version=version,
                description=description,
                messages=list(messages),
                model_config=dict(model_config or {}),
                created_at=now,
                updated_at=now,
                metadata=dict(metadata or {}),
            )
            self._write(name, {"name": name, "versions": [record.to_dict()]})
            return record

    def add_version(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: Optional[str] = None,
        model_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptRecord:
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"prompt {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "minor")
            now = _now()
            record = PromptRecord(
                name=name,
                version=new_version,
                description=description if description is not None else prev.get("description", ""),
                messages=list(messages),
                model_config=model_config if model_config is not None else prev.get("model_config", {}),
                created_at=now,
                updated_at=now,
                metadata={**prev.get("metadata", {}), **(metadata or {})},
            )
            versions.append(record.to_dict())
            data["versions"] = versions
            self._write(name, data)
            return record

    def update_messages(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> PromptRecord:
        with self._lock:
            data = self._read(name)
            versions = data.get("versions", [])
            if not versions:
                raise KeyError(f"prompt {name!r} has no versions")
            prev = versions[-1]
            new_version = _bump_version(prev.get("version", "1.0.0"), "patch")
            now = _now()
            record = PromptRecord(
                name=name,
                version=new_version,
                description=description if description is not None else prev.get("description", ""),
                messages=list(messages),
                model_config=prev.get("model_config", {}),
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

    def diff(self, name: str, v1: str, v2: str) -> Dict[str, Any]:
        with self._lock:
            r1 = self.get(name, v1)
            r2 = self.get(name, v2)
        return _diff_messages(r1.messages, r2.messages)


def _diff_messages(
    messages_a: List[Dict[str, Any]],
    messages_b: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute a message-level diff between two prompt versions."""
    a_map: Dict[int, Dict[str, Any]] = {i: m for i, m in enumerate(messages_a)}
    b_map: Dict[int, Dict[str, Any]] = {i: m for i, m in enumerate(messages_b)}

    a_keys = set(a_map)
    b_keys = set(b_map)

    added = [b_map[k] for k in sorted(b_keys - a_keys)]
    removed = [a_map[k] for k in sorted(a_keys - b_keys)]

    modified: List[Dict[str, Any]] = []
    for k in sorted(a_keys & b_keys):
        ma = a_map[k]
        mb = b_map[k]
        if _normalize(ma) == _normalize(mb):
            continue
        field_changes: Dict[str, Dict[str, Any]] = {}
        all_fields = set(ma) | set(mb)
        for fname in all_fields:
            va = ma.get(fname)
            vb = mb.get(fname)
            if _normalize(va) != _normalize(vb):
                field_changes[fname] = {"from": va, "to": vb}
        modified.append({"index": k, "fields": field_changes, "before": ma, "after": mb})

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
