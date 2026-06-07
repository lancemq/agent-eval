"""Tests for the orchestrator."""

from unittest.mock import MagicMock
from agent_eval.orchestrator import (
    EvaluationOrchestrator,
    EvaluationReport,
    TaskQueue,
    TaskPriority,
    TaskStatus,
)
from agent_eval.plugins.base import register_plugin
from agent_eval.plugins.base import BasePlugin, EvaluationType, EvalResult


@register_plugin
class MockPlugin(BasePlugin):
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
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.5 + task["id"] * 0.1,
            raw_score={},
            details={"task_id": task["id"]},
            artifacts=[output],
            passed=task["id"] < 2,
            execution_time_ms=10,
            task_id=str(task["id"]),
        )


@register_plugin
class FailingPlugin(BasePlugin):
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
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=0.0,
            raw_score={},
            details={},
            artifacts=[],
            passed=False,
            execution_time_ms=0,
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
    assert "mock_plugin" in report.plugin_results
    assert report.plugin_results["mock_plugin"]["passed"] == 2
    assert report.plugin_results["mock_plugin"]["total"] == 3


def test_orchestrator_with_failing_plugin():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["failing_plugin"])

    assert report.plugin_results["failing_plugin"]["total"] == 1
    assert report.plugin_results["failing_plugin"]["passed"] == 0


def test_orchestrator_multi_plugin():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"
    agent.generate.return_value = "test"

    orch = EvaluationOrchestrator()
    report = orch.run_evaluation(agent, ["mock_plugin", "failing_plugin"])

    assert report.summary["num_plugins"] == 2
    assert report.summary["total_tasks"] == 4


def test_task_queue_basic():
    queue = TaskQueue()
    task_id = queue.enqueue({"test": "data"}, plugin_name="test")
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
            "num_plugins": 2,
        },
        plugin_results={
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