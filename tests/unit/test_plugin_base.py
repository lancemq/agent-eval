"""Tests for base plugin system."""

import pytest
from agent_eval.plugins.base import (
    BasePlugin,
    EvaluationType,
    EvalContext,
    EvalResult,
    PluginRegistry,
    register_plugin,
)
from agent_eval.utils import resolve_config_path


def test_evaluation_type_values():
    assert EvaluationType.BENCHMARK.value == "benchmark"
    assert EvaluationType.DYNAMIC.value == "dynamic"
    assert EvaluationType.ADVERSARIAL.value == "adversarial"
    assert EvaluationType.CUSTOM.value == "custom"


def test_eval_context_defaults():
    ctx = EvalContext(agent_under_test="test", task_config={})
    assert ctx.agent_under_test == "test"
    assert ctx.task_config == {}
    assert ctx.environment is None
    assert ctx.metadata == {}
    assert ctx.run_id == ""
    assert ctx.timestamp == ""


def test_eval_result_creation():
    result = EvalResult(
        plugin_name="test_plugin",
        evaluation_type=EvaluationType.BENCHMARK,
        score=0.85,
        raw_score={"accuracy": 0.85},
        details={"correct": 85, "total": 100},
        artifacts=["output.txt"],
        passed=True,
        execution_time_ms=1500,
    )
    assert result.plugin_name == "test_plugin"
    assert result.score == 0.85
    assert result.passed is True


def test_plugin_registry():
    @register_plugin
    class TempTestPlugin(BasePlugin):
        name = "temp_test_plugin"
        evaluation_type = EvaluationType.CUSTOM
        supported_dimensions = ["test"]

        def setup(self, config):
            super().setup(config)
            self._config = config

        def generate_tasks(self, context):
            return [{"id": 1, "prompt": "test"}]

        def execute_task(self, task, context):
            return "test_output"

        def evaluate(self, task, output, context):
            return EvalResult(
                plugin_name=self.name,
                evaluation_type=self.evaluation_type,
                score=1.0,
                raw_score={},
                details={},
                artifacts=[output],
                passed=True,
                execution_time_ms=0,
            )

    assert "temp_test_plugin" in PluginRegistry.list_plugins()

    plugin = PluginRegistry.get("temp_test_plugin")
    assert plugin.name == "temp_test_plugin"
    assert isinstance(plugin, TempTestPlugin)
    assert not plugin.is_initialized

    plugin.setup({"key": "value"})
    assert plugin.is_initialized
    assert plugin.get_config("key") == "value"


def test_plugin_registry_double_register():
    @register_plugin
    class FirstPlugin(BasePlugin):
        name = "double_test_plugin"
        evaluation_type = EvaluationType.CUSTOM
        supported_dimensions = []

        def setup(self, config): pass
        def generate_tasks(self, context): return []
        def execute_task(self, task, context): return None
        def evaluate(self, task, output, context):
            return EvalResult(plugin_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)

    with pytest.raises(ValueError, match="already registered"):

        @register_plugin
        class DuplicatePlugin(BasePlugin):
            name = "double_test_plugin"

            def setup(self, config): pass
            def generate_tasks(self, context): return []
            def execute_task(self, task, context): return None
            def evaluate(self, task, output, context):
                return EvalResult(plugin_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)


def test_plugin_registry_get_nonexistent():
    with pytest.raises(ValueError, match="not found"):
        PluginRegistry.get("nonexistent_plugin_xyz")


def test_plugin_lifecycle():
    @register_plugin
    class LifecycleTestPlugin(BasePlugin):
        name = "lifecycle_test_plugin"
        evaluation_type = EvaluationType.CUSTOM
        supported_dimensions = ["test"]
        teardown_called = False

        def setup(self, config):
            pass

        def generate_tasks(self, context):
            return [{"id": 1, "prompt": "test"}]

        def execute_task(self, task, context):
            return "test_output"

        def evaluate(self, task, output, context):
            return EvalResult(
                plugin_name=self.name,
                evaluation_type=self.evaluation_type,
                score=1.0,
                raw_score={},
                details={},
                artifacts=[output],
                passed=True,
                execution_time_ms=0,
            )

        def teardown(self):
            self.teardown_called = True

    plugin = PluginRegistry.get("lifecycle_test_plugin")
    plugin.setup({})
    ctx = EvalContext(agent_under_test="agent", task_config={})

    tasks = plugin.generate_tasks(ctx)
    assert len(tasks) == 1
    assert tasks[0]["id"] == 1

    output = plugin.execute_task(tasks[0], ctx)
    assert output == "test_output"

    result = plugin.evaluate(tasks[0], output, ctx)
    assert result.passed is True
    assert result.score == 1.0

    plugin.teardown()


def test_register_plugin_decorator():
    @register_plugin
    class DecoratedTestPlugin(BasePlugin):
        name = "decorated_test_registry"
        evaluation_type = EvaluationType.CUSTOM
        supported_dimensions = ["test"]

        def setup(self, config):
            pass

        def generate_tasks(self, context):
            return []

        def execute_task(self, task, context):
            return None

        def evaluate(self, task, output, context):
            return EvalResult(
                plugin_name=self.name,
                evaluation_type=self.evaluation_type,
                score=0.5,
                raw_score={},
                details={},
                artifacts=[],
                passed=True,
                execution_time_ms=0,
            )

    assert "decorated_test_registry" in PluginRegistry.list_plugins()


def test_plugin_list_plugins():
    @register_plugin
    class ListTestPlugin(BasePlugin):
        name = "list_test_plugin"
        version = "2.0"
        evaluation_type = EvaluationType.DYNAMIC
        supported_dimensions = ["dim1", "dim2"]
        description = "Test listing"

        def setup(self, config): pass
        def generate_tasks(self, context): return []
        def execute_task(self, task, context): return None
        def evaluate(self, task, output, context):
            return EvalResult(plugin_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)

    plugins = PluginRegistry.list_plugins()
    info = plugins["list_test_plugin"]
    assert info["version"] == "2.0"
    assert info["type"] == "dynamic"
    assert "dim1" in info["dimensions"]
    assert info["description"] == "Test listing"


def test_resolve_config_path_uses_config_dir(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    resolved = resolve_config_path("scenarios/tool_use.yaml", {"_config_dir": str(config_dir)})
    assert resolved == str(config_dir / "scenarios" / "tool_use.yaml")
