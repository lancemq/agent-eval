"""Evaluator LLM model configuration store with secret masking."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


DEFAULT_EVAL_MODEL = {
    "model": "gpt-4o-mini",
    "api_key": "",
    "base_url": "",
    "timeout": 60.0,
}


class EvalModelConfigStore:
    """Stores the evaluator/judge LLM model config with api_key masking.

    Saved to .agent-eval/eval-model.json.
    The api_key is never exposed via the masked response (only
    ``api_key_configured: bool`` is returned), mirroring the Langfuse
    ``secret_configured`` pattern.
    """

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self.path = os.path.join(self.workspace, ".agent-eval", "eval-model.json")

    def load_raw(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return dict(DEFAULT_EVAL_MODEL)
        with open(self.path) as file:
            data = json.load(file)
        return {**DEFAULT_EVAL_MODEL, **data}

    def load_masked(self) -> Dict[str, Any]:
        raw = self.load_raw()
        return {
            "model": raw.get("model", DEFAULT_EVAL_MODEL["model"]),
            "base_url": raw.get("base_url", ""),
            "timeout": float(raw.get("timeout", DEFAULT_EVAL_MODEL["timeout"])),
            "api_key_configured": bool(raw.get("api_key")),
        }

    def save(self, update: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load_raw()
        api_key = update.get("api_key") or current.get("api_key", "")
        next_config = {
            "model": update.get("model", current.get("model", DEFAULT_EVAL_MODEL["model"])),
            "api_key": api_key,
            "base_url": update.get("base_url", current.get("base_url", "")),
            "timeout": float(update.get("timeout", current.get("timeout", DEFAULT_EVAL_MODEL["timeout"]))),
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as file:
            json.dump(next_config, file, indent=2, ensure_ascii=False)
        return self.load_masked()

    def load_for_scorer(self) -> Dict[str, Any]:
        """Full config (with api_key) for internal scorer use."""
        return self.load_raw()