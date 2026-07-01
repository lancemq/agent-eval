"""Configuration validation with detailed error messages.

Uses Pydantic v2 if available for rich schema validation,
otherwise falls back to built-in validation with dataclasses.

Usage:
    from agent_eval.config_schema import validate_config, ConfigError

    try:
        validate_config(raw_dict)
    except ConfigError as e:
        print(e.format_errors())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

VALID_ORCHESTRATOR_KEYS: Set[str] = {
    "max_workers", "max_task_retries", "agent_concurrency",
    "queue_backend", "storage", "log_level",
}

VALID_EVALUATOR_KEYS: Set[str] = {
    "enabled", "type", "module", "judges", "test_cases",
    "dataset", "subset", "sample_count", "scenario_file",
    "threshold", "timeout", "parallel", "attack_types",
    "difficulty", "config_dir",
}

VALID_REPORT_FORMATS: Set[str] = {"json", "html", "markdown", "csv", "xml"}

VALID_EVAL_TYPES: Set[str] = {"benchmark", "dynamic", "adversarial", "custom"}

VALID_LOG_LEVELS: Set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

VALID_QUEUE_BACKENDS: Set[str] = {"memory", "redis"}


@dataclass
class ConfigError:
    """A single configuration validation error."""
    path: str
    message: str
    value: Any = None
    suggestion: str = ""

    def __str__(self) -> str:
        loc = f"  [{self.path}]: " if self.path else "  "
        s = f"{loc}{self.message}"
        if self.value is not None:
            s += f" (got: {self.value!r})"
        if self.suggestion:
            s += f"\n        💡 {self.suggestion}"
        return s


@dataclass
class ValidationResult:
    """Result of config validation."""
    valid: bool
    errors: List[ConfigError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise ConfigValidationError(self.errors)

    def format_errors(self) -> str:
        lines = [f"Configuration validation failed with {len(self.errors)} error(s):"]
        for e in self.errors:
            lines.append(str(e))
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, errors: List[ConfigError]):
        self.errors = errors
        result = ValidationResult(valid=False, errors=errors)
        super().__init__(result.format_errors())


def _levenshtein(s1: str, s2: str) -> int:
    """Compute edit distance for typo suggestions."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dele = curr[j] + 1
            sub = prev[j] + (c1 != c2)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]


def _suggest(key: str, valid: Set[str], max_dist: int = 3) -> str:
    """Suggest the closest valid key for a typo."""
    best_match = ""
    best_dist = max_dist + 1
    for v in valid:
        d = _levenshtein(key.lower(), v.lower())
        if d < best_dist:
            best_dist = d
            best_match = v
    if best_match and best_dist <= max_dist:
        return f"Did you mean '{best_match}'?"
    return f"Valid keys: {sorted(valid)}"


def validate_config(raw: Dict[str, Any]) -> ValidationResult:
    """Validate a raw config dict before parsing.

    Args:
        raw: The raw configuration dictionary (from YAML/JSON)

    Returns:
        ValidationResult with errors and warnings
    """
    errors: List[ConfigError] = []
    warnings: List[str] = []

    if not isinstance(raw, dict):
        errors.append(ConfigError(path="", message="Config must be a dict/mapping"))
        return ValidationResult(valid=False, errors=errors)

    # Top-level keys
    valid_top_keys = {"orchestrator", "agent", "evaluators", "eval_config", "report"}
    for key in raw:
        if key not in valid_top_keys:
            errors.append(ConfigError(
                path=key, value=key,
                message=f"Unknown top-level key '{key}'",
                suggestion=_suggest(key, valid_top_keys),
            ))

    # Orchestrator
    orch = raw.get("orchestrator", {})
    if orch and not isinstance(orch, dict):
        errors.append(ConfigError(path="orchestrator", message="Must be a mapping"))
    elif isinstance(orch, dict):
        for key in orch:
            if key not in VALID_ORCHESTRATOR_KEYS:
                errors.append(ConfigError(
                    path=f"orchestrator.{key}", value=key,
                    message=f"Unknown orchestrator key '{key}'",
                    suggestion=_suggest(key, VALID_ORCHESTRATOR_KEYS),
                ))

        if "max_workers" in orch:
            mw = orch["max_workers"]
            if not isinstance(mw, int) or mw < 1:
                errors.append(ConfigError(
                    path="orchestrator.max_workers", value=mw,
                    message="Must be a positive integer",
                ))

        if "max_task_retries" in orch:
            mr = orch["max_task_retries"]
            if not isinstance(mr, int) or mr < 0:
                errors.append(ConfigError(
                    path="orchestrator.max_task_retries", value=mr,
                    message="Must be a non-negative integer",
                ))

        if "queue_backend" in orch:
            qb = str(orch["queue_backend"]).lower()
            if qb not in VALID_QUEUE_BACKENDS:
                errors.append(ConfigError(
                    path="orchestrator.queue_backend", value=qb,
                    message=f"Must be one of {sorted(VALID_QUEUE_BACKENDS)}",
                ))

        if "log_level" in orch:
            ll = str(orch["log_level"]).upper()
            if ll not in VALID_LOG_LEVELS:
                errors.append(ConfigError(
                    path="orchestrator.log_level", value=ll,
                    message=f"Must be one of {sorted(VALID_LOG_LEVELS)}",
                ))

    # Agent
    agent = raw.get("agent", {})
    if agent and not isinstance(agent, dict):
        errors.append(ConfigError(path="agent", message="Must be a mapping"))

    # Evaluators
    evaluators = raw.get("evaluators", {})
    if evaluators and not isinstance(evaluators, dict):
        errors.append(ConfigError(path="evaluators", message="Must be a mapping"))
    elif isinstance(evaluators, dict):
        for pname, pcfg in evaluators.items():
            if not isinstance(pcfg, dict):
                warnings.append(f"Evaluator '{pname}' has non-dict config, treating as enabled={bool(pcfg)}")
                continue
            for key in pcfg:
                if key not in VALID_EVALUATOR_KEYS:
                    # Evaluator-specific keys are allowed but warned
                    known_evaluator_keys = {
                        "mmlu": {"subset", "sample_count", "seed"},
                        "humaneval": {"dataset", "sample_count", "timeout", "language"},
                        "gsm8k": {"sample_count", "seed"},
                        "tool_use": {"scenario_file", "timeout"},
                        "multi_turn": {"scenario_file", "max_turns"},
                        "coding": {"scenario_file", "timeout", "language"},
                        "jailbreak": {"attack_types", "severity"},
                        "injection": {"attack_types"},
                        "bias": {"categories"},
                    }
                    evaluator_valid_keys = known_evaluator_keys.get(pname, set())
                    all_valid = VALID_EVALUATOR_KEYS | evaluator_valid_keys
                    if key not in all_valid:
                        warnings.append(
                            f"Evaluator '{pname}' has unknown key '{key}'. "
                            + _suggest(key, all_valid)
                        )

    # Report
    report = raw.get("report", {})
    if report and isinstance(report, dict):
        formats = report.get("formats", [])
        if isinstance(formats, str):
            formats = [formats]
        if isinstance(formats, list):
            for fmt in formats:
                if fmt not in VALID_REPORT_FORMATS:
                    errors.append(ConfigError(
                        path="report.formats", value=fmt,
                        message=f"Unknown format '{fmt}'",
                        suggestion=f"Valid formats: {sorted(VALID_REPORT_FORMATS)}",
                    ))

    # eval_config
    eval_cfg = raw.get("eval_config", {})
    if eval_cfg and not isinstance(eval_cfg, dict):
        errors.append(ConfigError(path="eval_config", message="Must be a mapping"))
    elif isinstance(eval_cfg, dict):
        if "priority" in eval_cfg:
            pri = str(eval_cfg["priority"]).lower()
            if pri not in ("low", "normal", "high", "critical"):
                errors.append(ConfigError(
                    path="eval_config.priority", value=pri,
                    message="Must be one of: low, normal, high, critical",
                ))

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_config_file(path: str) -> ValidationResult:
    """Load and validate a config file."""
    import os
    import json

    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
        except ImportError:
            raise RuntimeError("PyYAML required: pip install pyyaml")
    elif ext == ".json":
        with open(path) as f:
            raw = json.load(f)
    else:
        return ValidationResult(
            valid=False,
            errors=[ConfigError(path=path, message=f"Unsupported format: {ext}")]
        )

    return validate_config(raw)
