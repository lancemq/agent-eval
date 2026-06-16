"""Unified Web UI settings storage."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


DEFAULT_RUN_DEFAULTS = {
    "agent": "openai:gpt-4o-mini",
    "output_dir": "./eval_results",
    "report_formats": ["json", "html", "markdown"],
    "orchestrator": {
        "max_workers": 2,
        "queue_backend": "memory",
        "storage": {"type": "json", "output_dir": "./eval_results"},
        "log_level": "INFO",
    },
}


class WebSettingsStore:
    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self.path = os.path.join(self.workspace, ".agent-eval", "web-settings.json")

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"run_defaults": _deep_copy(DEFAULT_RUN_DEFAULTS)}
        with open(self.path) as file:
            data = json.load(file)
        return {"run_defaults": _merge_run_defaults(data.get("run_defaults", {}))}

    def save(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        next_settings = {"run_defaults": _merge_run_defaults(settings.get("run_defaults", {}))}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as file:
            json.dump(next_settings, file, indent=2, ensure_ascii=False)
        return self.load()


def _merge_run_defaults(update: Dict[str, Any]) -> Dict[str, Any]:
    defaults = _deep_copy(DEFAULT_RUN_DEFAULTS)
    orchestrator = {**defaults["orchestrator"], **update.get("orchestrator", {})}
    storage = {**defaults["orchestrator"]["storage"], **update.get("orchestrator", {}).get("storage", {})}
    orchestrator["storage"] = storage
    return {
        "agent": update.get("agent", defaults["agent"]),
        "output_dir": update.get("output_dir", defaults["output_dir"]),
        "report_formats": update.get("report_formats", defaults["report_formats"]),
        "orchestrator": orchestrator,
    }


def _deep_copy(value: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(value))
