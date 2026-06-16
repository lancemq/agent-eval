"""Langfuse integration helpers for the Web UI."""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List


DEFAULT_LANGFUSE_CONFIG = {
    "host": "https://cloud.langfuse.com",
    "public_key": "",
    "secret_key": "",
    "project": "",
    "enabled": False,
}


class LangfuseConfigStore:
    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self.path = os.path.join(self.workspace, ".agent-eval", "langfuse.json")

    def load_raw(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return dict(DEFAULT_LANGFUSE_CONFIG)
        with open(self.path) as file:
            data = json.load(file)
        return {**DEFAULT_LANGFUSE_CONFIG, **data}

    def load_masked(self) -> Dict[str, Any]:
        raw = self.load_raw()
        return {
            "host": raw.get("host", DEFAULT_LANGFUSE_CONFIG["host"]),
            "public_key": raw.get("public_key", ""),
            "project": raw.get("project", ""),
            "enabled": bool(raw.get("enabled", False)),
            "secret_configured": bool(raw.get("secret_key")),
        }

    def save(self, update: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load_raw()
        secret = update.get("secret_key") or current.get("secret_key", "")
        next_config = {
            "host": update.get("host", current.get("host", DEFAULT_LANGFUSE_CONFIG["host"])),
            "public_key": update.get("public_key", current.get("public_key", "")),
            "secret_key": secret,
            "project": update.get("project", current.get("project", "")),
            "enabled": bool(update.get("enabled", current.get("enabled", False))),
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as file:
            json.dump(next_config, file, indent=2, ensure_ascii=False)
        return self.load_masked()


class LangfuseClient:
    def __init__(self, config_store: LangfuseConfigStore):
        self.config_store = config_store

    def test_connection(self) -> Dict[str, Any]:
        config = self.config_store.load_raw()
        sessions = self.fetch_sessions(limit=1)
        return {"ok": True, "host": config.get("host"), "sessions_checked": len(sessions)}

    def fetch_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        params = {"limit": str(limit)}
        config = self.config_store.load_raw()
        if config.get("project"):
            params["project"] = config["project"]
        data = self._get("/api/public/sessions", params)
        return _extract_items(data)

    def fetch_session_traces(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        data = self._get("/api/public/traces", {"sessionId": session_id, "limit": str(limit)})
        return _extract_items(data)

    def fetch_trace(self, trace_id: str) -> Dict[str, Any]:
        return self._get(f"/api/public/traces/{urllib.parse.quote(trace_id, safe='')}", {})

    def _get(self, path: str, params: Dict[str, str]) -> Any:
        config = self.config_store.load_raw()
        if not config.get("public_key") or not config.get("secret_key"):
            raise ValueError("Langfuse public_key and secret_key are required")
        host = str(config.get("host") or DEFAULT_LANGFUSE_CONFIG["host"]).rstrip("/")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(f"{host}{path}{query}")
        token = base64.b64encode(f"{config['public_key']}:{config['secret_key']}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
        request.add_header("Accept", "application/json")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))


def _extract_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "items", "sessions", "traces"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def langfuse_trace_to_task(raw: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = str(raw.get("id") or raw.get("trace_id") or "")
    input_value = raw.get("input", raw.get("inputs", ""))
    output_value = raw.get("output", raw.get("outputs", ""))
    return {
        "task_id": trace_id,
        "task_type": "langfuse_trace",
        "input": _stringify_io(input_value),
        "expected": _stringify_io(output_value),
        "messages": raw.get("messages", []),
        "trajectory": raw.get("observations", raw.get("trajectory", [])),
        "available_tools": [],
        "success_criteria": {"expected_result": _stringify_io(output_value)},
        "scorers": [],
        "metadata": {
            "source": "langfuse",
            "langfuse_trace_id": trace_id,
            "langfuse_session_id": raw.get("sessionId", raw.get("session_id", "")),
            "name": raw.get("name", ""),
            "timestamp": raw.get("timestamp", raw.get("createdAt", "")),
        },
    }


def _stringify_io(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
