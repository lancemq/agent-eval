"""Tests for the orchestrator."""

import pytest
from unittest.mock import MagicMock
from agent_eval.orchestrator import (
    EvaluationOrchestrator,
    EvaluationReport,
    TaskQueue,
    TaskPriority,
    TaskStatus,
)
from agent_eval.evaluators.base import register_evaluator
from agent_eval.evaluators.base import BaseEvaluator, EvaluationType, EvalResult


@register_evaluator
class MockPlugin(BaseEvaluator):
    name = "mock_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["mock"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"id": i, "prompt": f"test_{i}"} for i in range(3)]

    def execute_task(self, task, context):
        return f"response_{task['id']}"

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.5 + task["id"] * 0.1,
            raw_score={},
            details={"task_id": task["id"]},
            artifacts=[output],
            passed=task["id"] < 2,
            execution_time_ms=10,
            task_id=str(task["id"]),
        )


@register_evaluator
class FailingPlugin(BaseEvaluator):
    name = "failing_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["fail"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"id": 1}]

    def execute_task(self, task, context):
        raise RuntimeError("Task execution failed")

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.0,
            raw_score={},
            details={},
            artifacts=[],
            passed=False,
            execution_time_ms=0,
        )


@register_evaluator
class ConfigPlugin(BaseEvaluator):
    name = "config_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["config"]

    def setup(self, config):
        self.config_value = config["value"]

    def generate_tasks(self, context):
        return [{"id": "config"}]

    def execute_task(self, task, context):
        return self.config_value

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=1.0 if output == "expected" else 0.0,
            raw_score={"output": output},
            details={},
            artifacts=[],
            passed=output == "expected",
            execution_time_ms=0,
            task_id=task["id"],
        )


@register_evaluator
class StatefulPlugin(BaseEvaluator):
    name = "stateful_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["state"]
    teardown_count = 0

    def setup(self, config):
        self.seen = getattr(self, "seen", 0) + 1

    def generate_tasks(self, context):
        return [{"id": "state"}]

    def execute_task(self, task, context):
        return self.seen

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=1.0 if output == 1 else 0.0,
            raw_score={"seen": output},
            details={},
            artifacts=[],
            passed=output == 1,
            execution_time_ms=0,
            task_id=task["id"],
        )

    def teardown(self):
        type(self).teardown_count += 1


@register_evaluator
class SetupFailingPlugin(BaseEvaluator):
    name = "setup_failing_plugin"
    evaluation_type = EvaluationType.CUSTOM

    def setup(self, config):
        raise RuntimeError("setup failed")

    def generate_tasks(self, context):
        return []

    def execute_task(self, task, context):
        return None

    def evaluate(self, task, output, context):
        raise AssertionError("should not evaluate")


@register_evaluator
class GenerateFailingPlugin(BaseEvaluator):
    name = "generate_failing_plugin"
    evaluation_type = EvaluationType.CUSTOM
    teardown_count = 0

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        raise RuntimeError("generate failed")

    def execute_task(self, task, context):
        return None

    def evaluate(self, task, output, context):
        raise AssertionError("should not evaluate")

    def teardown(self):
        type(self).teardown_count += 1


@register_evaluator
class FlakyPlugin(BaseEvaluator):
    name = "flaky_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["retry"]

    def setup(self, config):
        self.calls = 0

    def generate_tasks(self, context):
        return [{"task_id": "flaky"}]

    def execute_task(self, task, context):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return "ok"

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=1.0,
            raw_score={"output": output},
            details={},
            artifacts=[],
            passed=True,
            execution_time_ms=0,
            task_id=task["task_id"],
        )


def test_orchestrator_initialization():
    from agent_eval.config import OrchestratorConfig
    config = OrchestratorConfig(max_workers=2)
    orch = EvaluationOrchestrator(config)
    assert orch.config.max_workers == 2


def test_orchestrator_run_evaluation():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"
    agent.generate.return_value = "test response"
    agent.chat.return_value = "test chat"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["mock_plugin"])

    assert isinstance(report, EvaluationReport)
    assert report.run_id is not None
    assert report.agent_name == "test_agent"
    assert report.summary["total_tasks"] == 3
    assert report.summary["total_passed"] == 2
    assert report.summary["pass_rate"] == 2 / 3
    assert "mock_plugin" in report.evaluator_results
    assert report.evaluator_results["mock_plugin"]["passed"] == 2
    assert report.evaluator_results["mock_plugin"]["total"] == 3


def test_orchestrator_with_failing_plugin():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["failing_plugin"])

    assert report.evaluator_results["failing_plugin"]["total"] == 1
    assert report.evaluator_results["failing_plugin"]["passed"] == 0


def test_orchestrator_multi_plugin():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"
    agent.generate.return_value = "test"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["mock_plugin", "failing_plugin"])

    assert report.summary["num_evaluators"] == 2
    assert report.summary["total_tasks"] == 4


def test_task_queue_basic():
    queue = TaskQueue()
    task_id = queue.enqueue({"test": "data"}, evaluator_name="test")
    assert queue.size() == 1
    assert queue.total() == 1

    task = queue.dequeue()
    assert task is not None
    assert task.task_id == task_id
    assert task.data["test"] == "data"
    assert task.status == TaskStatus.RUNNING


def test_task_queue_priority():
    queue = TaskQueue()
    low_id = queue.enqueue({"priority": "low"}, priority=TaskPriority.LOW)
    high_id = queue.enqueue({"priority": "high"}, priority=TaskPriority.HIGH)

    task1 = queue.dequeue()
    assert task1.task_id == high_id
    task2 = queue.dequeue()
    assert task2.task_id == low_id


def test_task_queue_complete_fail():
    queue = TaskQueue()
    task_id = queue.enqueue({"test": True})
    queue.dequeue()

    queue.complete(task_id, {"result": "ok"})
    task = queue.get(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"result": "ok"}

    queue2 = TaskQueue()
    fail_id = queue2.enqueue({"test": True})
    queue2.dequeue()
    # Exhaust retries to get FAILED status
    for _ in range(4):
        fail_task = queue2.get(fail_id)
        if fail_task.status == TaskStatus.FAILED:
            break
        queue2.fail(fail_id, "error occurred")
    failed_task = queue2.get(fail_id)
    assert failed_task.status == TaskStatus.FAILED
    assert failed_task.error == "error occurred"


def test_task_queue_progress():
    queue = TaskQueue()
    ids = [queue.enqueue({"id": i}) for i in range(5)]

    for i in range(3):
        queue.dequeue()
        queue.complete(ids[i])

    progress = queue.progress()
    assert progress["total"] == 5
    assert progress["completed"] == 3
    assert progress["pending"] == 2


def test_task_queue_cancel():
    queue = TaskQueue()
    task_id = queue.enqueue({"test": True})
    queue.cancel(task_id)
    task = queue.get(task_id)
    assert task.status == TaskStatus.CANCELLED


def test_task_queue_retry():
    queue = TaskQueue()
    task_id = queue.enqueue({"test": True})
    queue.dequeue()
    queue.fail(task_id, "temp error")
    task = queue.get(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.retries == 1


def test_plugin_config_is_passed_to_setup():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(
        agent,
        ["config_plugin"],
        evaluator_configs={"config_plugin": {"value": "expected"}},
    )

    assert report.evaluator_results["config_plugin"]["passed"] == 1
    assert report.task_results["config_plugin"][0]["raw_score"] == {"output": "expected"}


def test_plugins_are_new_instances_per_run():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    first = orch.run_evaluation(agent, ["stateful_plugin"])
    second = orch.run_evaluation(agent, ["stateful_plugin"])

    assert first.task_results["stateful_plugin"][0]["raw_score"] == {"seen": 1}
    assert second.task_results["stateful_plugin"][0]["raw_score"] == {"seen": 1}


def test_teardown_runs_when_evaluation_fails_after_setup():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"
    before = GenerateFailingPlugin.teardown_count

    orch = EvaluationOrchestrator()
    with pytest.raises(RuntimeError, match="generate failed"):
        orch.run_evaluation(agent, ["generate_failing_plugin"])

    assert GenerateFailingPlugin.teardown_count == before + 1


def test_task_results_are_serialized_and_restored():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["mock_plugin"])
    restored = EvaluationReport.from_dict(report.to_dict())

    assert len(restored.task_results["mock_plugin"]) == 3
    assert restored.task_results["mock_plugin"][0]["evaluator_name"] == "mock_plugin"


def test_orchestrator_retries_failed_tasks_before_scoring_failure():
    from agent_eval.config import OrchestratorConfig

    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator(OrchestratorConfig(max_task_retries=1))
    report = orch.run_evaluation(agent, ["flaky_plugin"])

    result = report.task_results["flaky_plugin"][0]
    assert result["passed"] is True
    assert result["details"]["attempt"] == 2


def test_evaluation_report():
    report = EvaluationReport(
        run_id="test_run",
        timestamp="2024-01-01T00:00:00Z",
        agent_name="test_agent",
        agent_version="1.0",
        summary={
            "overall_score": 0.75,
            "total_tasks": 10,
            "total_passed": 7,
            "total_failed": 3,
            "pass_rate": 0.7,
            "dimensions": {"accuracy": 0.8, "speed": 0.7},
            "num_evaluators": 2,
        },
        evaluator_results={
            "plugin_a": {"score": 0.8, "passed": 4, "total": 5},
            "plugin_b": {"score": 0.7, "passed": 3, "total": 5},
        },
        metadata={"agent_name": "test_agent"},
    )

    assert report.run_id == "test_run"
    assert report.summary["overall_score"] == 0.75

    d = report.to_dict()
    assert d["run_id"] == "test_run"
    assert d["summary"]["pass_rate"] == 0.7

    restored = EvaluationReport.from_dict(d)
    assert restored.run_id == "test_run"
    assert restored.summary["overall_score"] == 0.75


@register_evaluator
class HeavyPlugin(BaseEvaluator):
    name = "heavy_plugin"
    evaluation_type = EvaluationType.BENCHMARK
    supported_dimensions = ["knowledge"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"id": i} for i in range(10)]

    def execute_task(self, task, context):
        return "ok"

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=1.0,
            raw_score={},
            details={},
            artifacts=[],
            passed=True,
            execution_time_ms=1,
            task_id=str(task["id"]),
        )


@register_evaluator
class LightPlugin(BaseEvaluator):
    name = "light_plugin"
    evaluation_type = EvaluationType.BENCHMARK
    supported_dimensions = ["knowledge"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"id": 0}]

    def execute_task(self, task, context):
        return "ok"

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.0,
            raw_score={},
            details={},
            artifacts=[],
            passed=False,
            execution_time_ms=1,
            task_id=str(task["id"]),
        )


@register_evaluator
class DimensionPlugin(BaseEvaluator):
    name = "dimension_plugin"
    evaluation_type = EvaluationType.DYNAMIC
    supported_dimensions = ["planning", "tool_calling"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"id": 0}, {"id": 1}]

    def execute_task(self, task, context):
        return "ok"

    def evaluate(self, task, output, context):
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.5,
            raw_score={},
            details={},
            artifacts=[],
            passed=True,
            execution_time_ms=1,
            task_id=str(task["id"]),
            dimension_scores={"planning": 0.3 if task["id"] == 0 else 0.7, "tool_calling": 0.8},
        )


def test_micro_and_macro_scores():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["heavy_plugin", "light_plugin"])

    # macro = (1.0 + 0.0) / 2 = 0.5
    # micro = (10*1.0 + 1*0.0) / 11 = ~0.909
    assert abs(report.summary["macro_score"] - 0.5) < 0.001
    assert abs(report.summary["micro_score"] - 0.909) < 0.001
    assert abs(report.summary["overall_score"] - report.summary["micro_score"]) < 0.001


def test_dimension_scores_override_fallback():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["dimension_plugin"])

    # planning: (0.3 + 0.7) / 2 = 0.5
    # tool_calling: (0.8 + 0.8) / 2 = 0.8
    assert abs(report.summary["dimensions"]["planning"] - 0.5) < 0.001
    assert abs(report.summary["dimensions"]["tool_calling"] - 0.8) < 0.001
