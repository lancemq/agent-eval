import sys
from unittest.mock import MagicMock, patch

import pytest

from agent_eval.config import EvaluationConfig, PluginConfig
from agent_eval.runner import agent_spec_from_config, create_agent, import_plugin_modules, resolve_plugin_names, run_evaluation_from_config


def test_agent_spec_from_module_config():
    config = EvaluationConfig()
    config.agent.module = "pkg:Agent"
    assert agent_spec_from_config(config) == "pkg:Agent"


def test_agent_spec_from_model_config():
    config = EvaluationConfig()
    config.agent.config["model"] = "gpt-test"
    assert agent_spec_from_config(config) == "openai:gpt-test"


def test_agent_spec_requires_value():
    with pytest.raises(ValueError):
        agent_spec_from_config(EvaluationConfig())


def test_resolve_plugin_names_prefers_override():
    config = EvaluationConfig(plugins={"a": PluginConfig(enabled=True), "b": PluginConfig(enabled=False)})
    assert resolve_plugin_names(config, ["b"]) == ["b"]


def test_resolve_plugin_names_uses_enabled_plugins():
    config = EvaluationConfig(plugins={"a": PluginConfig(enabled=True), "b": PluginConfig(enabled=False)})
    assert resolve_plugin_names(config) == ["a"]


def test_create_agent_rejects_invalid_spec():
    with pytest.raises(ValueError):
        create_agent("invalid", {})


def test_import_plugin_modules(tmp_path):
    module_path = tmp_path / "sample_plugin_module.py"
    module_path.write_text("VALUE = 1\n")
    sys.path.insert(0, str(tmp_path))
    try:
        import_plugin_modules(["sample_plugin_module"])
        assert "sample_plugin_module" in sys.modules
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("sample_plugin_module", None)


@patch("agent_eval.runner.ReportGenerator")
@patch("agent_eval.runner.EvaluationOrchestrator")
@patch("agent_eval.runner.create_agent")
def test_run_evaluation_from_config(mock_create_agent, mock_orchestrator_cls, mock_generator_cls, tmp_path):
    config = EvaluationConfig(plugins={"mock": PluginConfig(enabled=True, config={"x": 1})})
    config.agent.config["model"] = "gpt-test"
    report = MagicMock()
    report.summary = {"overall_score": 1.0}
    orchestrator = mock_orchestrator_cls.return_value
    orchestrator.run_evaluation.return_value = report
    mock_generator_cls.return_value.generate.return_value = {"json": "report.json"}

    result = run_evaluation_from_config(config, output_dir=str(tmp_path))

    assert result.report is report
    assert result.generated_reports == {"json": "report.json"}
    mock_create_agent.assert_called_once_with("openai:gpt-test", {"model": "gpt-test"})
    orchestrator.run_evaluation.assert_called_once()
