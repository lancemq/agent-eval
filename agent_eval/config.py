"""Configuration system for evaluation."""

import json
import os
from typing import Any, Dict
from dataclasses import dataclass, field


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    max_workers: int = 4
    max_task_retries: int = 3
    agent_concurrency: int = 0
    queue_backend: str = "memory"
    storage: Dict[str, Any] = field(default_factory=lambda: {"type": "json", "output_dir": "./eval_results"})
    log_level: str = "INFO"


@dataclass
class PluginConfig:
    """Configuration for a single plugin."""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for the agent under test."""
    type: str = "callable"
    module: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationConfig:
    """Top-level evaluation configuration."""
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    plugins: Dict[str, PluginConfig] = field(default_factory=dict)
    plugin_modules: list[str] = field(default_factory=list)
    eval_config: Dict[str, Any] = field(default_factory=dict)
    report: Dict[str, Any] = field(default_factory=lambda: {"formats": ["json", "html"], "output_dir": "./eval_results"})
    config_dir: str = ""


def load_config(path: str, validate: bool = True) -> EvaluationConfig:
    """Load configuration from file.

    Args:
        path: Path to YAML or JSON config file
        validate: If True, validate config before parsing (default: True)
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext in (".yaml", ".yml"):
        try:
            import yaml
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
        except ImportError:
            raise RuntimeError("PyYAML required for yaml config: pip install pyyaml")
    elif ext == ".json":
        with open(path) as f:
            raw = json.load(f)
    else:
        raise ValueError(f"Unsupported config format: {ext}")

    if validate:
        from agent_eval.config_schema import validate_config
        result = validate_config(raw)
        if not result.valid:
            raise ValueError(result.format_errors())
        for warning in result.warnings:
            import logging
            logging.getLogger("agent_eval.config").warning(warning)

    return parse_config(raw, base_dir=os.path.dirname(os.path.abspath(path)))


def parse_config(raw: Dict[str, Any], base_dir: str = "") -> EvaluationConfig:
    """Parse raw dict into EvaluationConfig."""
    orch_raw = raw.get("orchestrator", {})
    orch = OrchestratorConfig(
        max_workers=orch_raw.get("max_workers", 4),
        max_task_retries=orch_raw.get("max_task_retries", 3),
        agent_concurrency=orch_raw.get("agent_concurrency", 0),
        queue_backend=orch_raw.get("queue_backend", "memory"),
        storage=orch_raw.get("storage", {"type": "json", "output_dir": "./eval_results"}),
        log_level=orch_raw.get("log_level", "INFO"),
    )

    agent_raw = raw.get("agent", {})
    agent = AgentConfig(
        type=agent_raw.get("type", "callable"),
        module=agent_raw.get("module", ""),
        config=agent_raw.get("config", {}),
    )

    plugins = {}
    for name, cfg in raw.get("plugins", {}).items():
        if isinstance(cfg, dict):
            plugins[name] = PluginConfig(
                enabled=cfg.get("enabled", True),
                config={k: v for k, v in cfg.items() if k != "enabled"},
            )
        else:
            plugins[name] = PluginConfig(enabled=bool(cfg))

    report_raw = raw.get("report", {})
    report = {
        "formats": report_raw.get("formats", ["json", "html"]),
        "output_dir": report_raw.get("output_dir", "./eval_results"),
    }

    return EvaluationConfig(
        orchestrator=orch,
        agent=agent,
        plugins=plugins,
        plugin_modules=raw.get("plugin_modules", []),
        eval_config=raw.get("eval_config", {}),
        report=report,
        config_dir=base_dir,
    )
