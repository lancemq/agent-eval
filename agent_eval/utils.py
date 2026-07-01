"""Utility functions."""

import json
import os
from typing import Dict, Optional


def generate_run_id() -> str:
    """Generate a unique run ID."""
    import uuid
    return str(uuid.uuid4())


def timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def safe_json_loads(text: str) -> Optional[Dict]:
    """Safely parse JSON from text, handling code block fences."""
    import re
    json_match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def ensure_dir(path: str) -> str:
    """Ensure directory exists, create if needed."""
    os.makedirs(path, exist_ok=True)
    return path


def weighted_average(values: Dict[str, float], weights: Dict[str, float]) -> float:
    """Compute weighted average."""
    total_weight = 0.0
    weighted_sum = 0.0
    for key, value in values.items():
        weight = weights.get(key, 1.0)
        weighted_sum += value * weight
        total_weight += weight
    return weighted_sum / total_weight if total_weight > 0 else 0.0


def extract_json_from_response(text: str) -> Optional[Dict]:
    """Extract JSON object from LLM response text."""
    import re
    patterns = [
        r"\{[^{}]*\}",
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def format_score(score: float, precision: int = 3) -> str:
    """Format score with bar visualization."""
    bar = "█" * int(score * 20)
    return f"{score:.{precision}f} {bar}"


def resolve_config_path(path: str, config: Dict) -> str:
    """Resolve evaluator file paths relative to the evaluation config file."""
    if not path or os.path.isabs(path):
        return path
    base_dir = config.get("_config_dir")
    if base_dir:
        return os.path.abspath(os.path.join(base_dir, path))
    return path
