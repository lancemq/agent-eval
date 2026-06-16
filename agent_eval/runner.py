"""Shared runner utilities for CLI and Web UI."""

import importlib
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from agent_eval.agents import AgentFactory
from agent_eval.config import EvaluationConfig
from agent_eval.orchestrator import AgentUnderTest, EvaluationOrchestrator
from agent_eval.reporting import ReportGenerator


class EvaluationRunResult:
    def __init__(self, report, generated_reports: Dict[str, str]):
        self.report = report
        self.generated_reports = generated_reports


def create_agent(agent_str: str, config: Dict[str, Any]) -> AgentUnderTest:
    return AgentFactory.create(agent_str, config)


def agent_spec_from_config(config: EvaluationConfig, override_agent: Optional[str] = None) -> str:
    if override_agent:
        return override_agent
    if config.agent.module:
        return config.agent.module
    model = config.agent.config.get("model")
    if model:
        return f"openai:{model}"
    raise ValueError("Agent spec is required. Provide --agent, agent.module, or agent.config.model")


def resolve_plugin_names(config: EvaluationConfig, override_plugins: Optional[List[str]] = None) -> List[str]:
    if override_plugins:
        return override_plugins
    return [name for name, plugin_config in config.plugins.items() if plugin_config.enabled]


def run_evaluation_from_config(
    config: EvaluationConfig,
    agent_spec: Optional[str] = None,
    plugin_names: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    orchestrator: Optional[EvaluationOrchestrator] = None,
) -> EvaluationRunResult:
    import_plugin_modules(config.plugin_modules)
    selected_agent = agent_spec_from_config(config, agent_spec)
    selected_plugins = resolve_plugin_names(config, plugin_names)

    if output_dir:
        config.orchestrator.storage["output_dir"] = output_dir
        config.report["output_dir"] = output_dir

    agent = create_agent(selected_agent, config.agent.config)
    orchestrator = orchestrator or EvaluationOrchestrator(config.orchestrator)
    plugin_configs = {name: plugin_config.config for name, plugin_config in config.plugins.items()}
    report = orchestrator.run_evaluation(agent, selected_plugins, config.eval_config, plugin_configs)

    report_output_dir = output_dir or config.report.get("output_dir", "./eval_results")
    generator = ReportGenerator(report_output_dir)
    generated = generator.generate(report, config.report.get("formats", ["json", "html", "markdown"]))
    return EvaluationRunResult(report, generated)


def import_plugin_modules(plugin_modules: List[str]) -> None:
    for module in plugin_modules:
        importlib.import_module(module)


def config_to_dict(config: EvaluationConfig) -> Dict[str, Any]:
    return asdict(config)
