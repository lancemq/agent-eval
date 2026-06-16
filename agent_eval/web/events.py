"""Event bus for Web UI run updates."""

import json
import queue
from datetime import datetime, timezone
from typing import Any, Dict, Iterator


class EventBus:
    def __init__(self):
        self._queues: Dict[str, queue.Queue] = {}

    def create_run(self, run_id: str) -> None:
        self._queues[run_id] = queue.Queue()

    def publish(self, run_id: str, event_type: str, payload: Dict[str, Any] = None) -> None:
        if run_id not in self._queues:
            self.create_run(run_id)
        event = {
            "type": event_type,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **(payload or {}),
        }
        self._queues[run_id].put(event)

    def stream(self, run_id: str) -> Iterator[Dict[str, str]]:
        if run_id not in self._queues:
            self.create_run(run_id)
        events = self._queues[run_id]
        while True:
            event = events.get()
            yield {"event": event["type"], "data": json.dumps(event)}
            if event["type"] in {"evaluation_complete", "evaluation_failed", "run_not_found"}:
                break

    def attach_orchestrator_hooks(self, run_id: str, orchestrator) -> None:
        orchestrator.hooks.register("evaluation_start", lambda context: self.publish(
            run_id,
            "evaluation_start",
            {"actual_run_id": context.run_id, "agent_name": context.metadata.get("agent_name")},
        ))
        orchestrator.hooks.register("plugin_setup", lambda plugin: self.publish(
            run_id,
            "plugin_setup",
            {"plugin": plugin.name},
        ))
        orchestrator.hooks.register("plugin_teardown", lambda plugin: self.publish(
            run_id,
            "plugin_teardown",
            {"plugin": plugin.name},
        ))
        orchestrator.hooks.register("task_generated", lambda plugin, tasks: self.publish(
            run_id,
            "task_generated",
            {"plugin": plugin.name, "count": len(tasks)},
        ))
        orchestrator.hooks.register("task_execute", lambda plugin, task: self.publish(
            run_id,
            "task_execute",
            {"plugin": plugin.name, "task": _safe_task(task)},
        ))
        orchestrator.hooks.register("task_evaluate", lambda plugin, task, output: self.publish(
            run_id,
            "task_evaluate",
            {"plugin": plugin.name, "task": _safe_task(task)},
        ))
        orchestrator.hooks.register("task_complete", lambda task_id, result: self.publish(
            run_id,
            "task_complete",
            {
                "task_id": task_id,
                "plugin": result.plugin_name,
                "score": result.score,
                "passed": result.passed,
                "error": result.error,
            },
        ))
        orchestrator.hooks.register("task_failed", lambda task_id, error: self.publish(
            run_id,
            "task_failed",
            {"task_id": task_id, "error": str(error)},
        ))
        orchestrator.hooks.register("evaluation_complete", lambda report: self.publish(
            run_id,
            "evaluation_complete",
            {"report_id": report.run_id, "summary": report.summary},
        ))


def _safe_task(task: Any) -> Any:
    if isinstance(task, dict):
        return {k: v for k, v in task.items() if k.lower() not in {"answer", "expected", "secret", "api_key"}}
    return str(task)
