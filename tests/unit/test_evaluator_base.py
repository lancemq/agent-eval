"""Tests for base evaluator system."""

import pytest
from agent_eval.evaluators.base import (
    BaseEvaluator,
    EvaluationType,
    EvalContext,
    EvalResult,
    EvaluatorRegistry,
    register_evaluator,
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
        evaluator_name="test_plugin",
        evaluation_type=EvaluationType.BENCHMARK,
        score=0.85,
        raw_score={"accuracy": 0.85},
        details={"correct": 85, "total": 100},
        artifacts=["output.txt"],
        passed=True,
        execution_time_ms=1500,
    )
    assert result.evaluator_name == "test_plugin"
    assert result.score == 0.85
    assert result.passed is True


def test_plugin_registry():
    @register_evaluator
    class TempTestPlugin(BaseEvaluator):
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
                evaluator_name=self.name,
                evaluation_type=self.evaluation_type,
                score=1.0,
                raw_score={},
                details={},
                artifacts=[output],
                passed=True,
                execution_time_ms=0,
            )

    assert "temp_test_plugin" in EvaluatorRegistry.list_evaluators()

    evaluator = EvaluatorRegistry.get("temp_test_plugin")
    assert evaluator.name == "temp_test_plugin"
    assert isinstance(evaluator, TempTestPlugin)
    assert not evaluator.is_initialized

    evaluator.setup({"key": "value"})
    assert evaluator.is_initialized
    assert evaluator.get_config("key") == "value"


def test_plugin_registry_double_register():
    @register_evaluator
    class FirstPlugin(BaseEvaluator):
        name = "double_test_plugin"
        evaluation_type = EvaluationType.CUSTOM
        supported_dimensions = []

        def setup(self, config): pass
        def generate_tasks(self, context): return []
        def execute_task(self, task, context): return None
        def evaluate(self, task, output, context):
            return EvalResult(evaluator_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)

    with pytest.raises(ValueError, match="already registered"):

        @register_evaluator
        class DuplicatePlugin(BaseEvaluator):
            name = "double_test_plugin"

            def setup(self, config): pass
            def generate_tasks(self, context): return []
            def execute_task(self, task, context): return None
            def evaluate(self, task, output, context):
                return EvalResult(evaluator_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)


def test_plugin_registry_get_nonexistent():
    with pytest.raises(ValueError, match="not found"):
        EvaluatorRegistry.get("nonexistent_plugin_xyz")


def test_plugin_lifecycle():
    @register_evaluator
    class LifecycleTestPlugin(BaseEvaluator):
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
                evaluator_name=self.name,
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

    evaluator = EvaluatorRegistry.get("lifecycle_test_plugin")
    evaluator.setup({})
    ctx = EvalContext(agent_under_test="agent", task_config={})

    tasks = evaluator.generate_tasks(ctx)
    assert len(tasks) == 1
    assert tasks[0]["id"] == 1

    output = evaluator.execute_task(tasks[0], ctx)
    assert output == "test_output"

    result = evaluator.evaluate(tasks[0], output, ctx)
    assert result.passed is True
    assert result.score == 1.0

    evaluator.teardown()


def test_register_plugin_decorator():
    @register_evaluator
    class DecoratedTestPlugin(BaseEvaluator):
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
                evaluator_name=self.name,
                evaluation_type=self.evaluation_type,
                score=0.5,
                raw_score={},
                details={},
                artifacts=[],
                passed=True,
                execution_time_ms=0,
            )

    assert "decorated_test_registry" in EvaluatorRegistry.list_evaluators()


def test_plugin_list_plugins():
    @register_evaluator
    class ListTestPlugin(BaseEvaluator):
        name = "list_test_plugin"
        version = "2.0"
        evaluation_type = EvaluationType.DYNAMIC
        supported_dimensions = ["dim1", "dim2"]
        description = "Test listing"

        def setup(self, config): pass
        def generate_tasks(self, context): return []
        def execute_task(self, task, context): return None
        def evaluate(self, task, output, context):
            return EvalResult(evaluator_name=self.name, evaluation_type=self.evaluation_type, score=0.0, raw_score={}, details={}, artifacts=[], passed=True, execution_time_ms=0)

    evaluators = EvaluatorRegistry.list_evaluators()
    info = evaluators["list_test_plugin"]
    assert info["version"] == "2.0"
    assert info["type"] == "dynamic"
    assert "dim1" in info["dimensions"]
    assert info["description"] == "Test listing"


def test_resolve_config_path_uses_config_dir(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    resolved = resolve_config_path("scenarios/tool_use.yaml", {"_config_dir": str(config_dir)})
    assert resolved == str(config_dir / "scenarios" / "tool_use.yaml")
