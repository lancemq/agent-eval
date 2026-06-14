"""Redis-backed distributed task queue for multi-worker evaluation.

Enables running evaluation tasks across multiple machines/processes
using Redis as the message broker.

Usage:
    # Worker process
    from agent_eval.distributed import RedisTaskQueue, EvaluationWorker

    queue = RedisTaskQueue(redis_url="redis://localhost:6379")
    worker = EvaluationWorker(queue, plugins=["mmlu", "gsm8k"])
    worker.start()  # Polls for tasks

    # Submitter
    queue.submit_tasks(tasks, plugin_name="mmlu", priority="high")
    results = queue.collect_results(run_id, timeout=300)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_eval.orchestrator.task_queue import TaskPriority

logger = logging.getLogger("agent_eval.distributed")


class RedisTaskQueue:
    """Redis-backed priority task queue.

    Uses Redis sorted sets for priority ordering and pub/sub for
    real-time result collection.

    Requires: pip install redis
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        queue_name: str = "agent_eval:tasks",
        results_channel: str = "agent_eval:results",
    ):
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.results_channel = results_channel
        self._redis: Any = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            try:
                import redis
            except ImportError as e:
                raise RuntimeError("redis library required: pip install redis") from e
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def submit_tasks(
        self,
        tasks: List[Dict[str, Any]],
        plugin_name: str = "",
        priority: str = "normal",
        run_id: str = "",
    ) -> List[str]:
        """Submit tasks to the queue."""
        r = self._get_redis()
        priority_map = {
            "low": TaskPriority.LOW, "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH, "critical": TaskPriority.CRITICAL,
        }
        pri = priority_map.get(priority, TaskPriority.NORMAL)
        # Lower score = higher priority in Redis sorted set
        score = -pri.value + time.time() * 1e-9

        task_ids: List[str] = []
        pipe = r.pipeline()
        for task_data in tasks:
            task_id = task_data.get("task_id", str(uuid.uuid4()))
            task_data["_plugin"] = plugin_name
            task_data["_run_id"] = run_id
            task_data["_status"] = "pending"
            pipe.zadd(self.queue_name, {json.dumps({"task_id": task_id, "data": task_data}): score})
            pipe.hset(f"agent_eval:task:{task_id}", mapping=task_data)
            task_ids.append(task_id)
        pipe.execute()
        logger.info(f"Submitted {len(task_ids)} tasks for plugin '{plugin_name}'")
        return task_ids

    def claim_task(self, worker_id: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Atomically claim the highest-priority task from the queue."""
        r = self._get_redis()

        # Use ZPOPMIN for atomic claim of highest priority
        result = r.zpopmin(self.queue_name, count=1)
        if not result:
            return None

        raw_item, _ = result[0]
        item = json.loads(raw_item)
        task_id = item["task_id"]

        # Mark as running
        r.hset(f"agent_eval:task:{task_id}", mapping={
            "_status": "running",
            "_worker": worker_id,
            "_started_at": str(time.time()),
        })
        return item["data"]

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark a task as completed and publish result."""
        r = self._get_redis()
        r.hset(f"agent_eval:task:{task_id}", mapping={
            "_status": "completed",
            "_completed_at": str(time.time()),
        })
        r.publish(self.results_channel, json.dumps({"task_id": task_id, "result": result}))

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        r = self._get_redis()
        r.hset(f"agent_eval:task:{task_id}", mapping={
            "_status": "failed",
            "_error": error,
            "_failed_at": str(time.time()),
        })
        r.publish(self.results_channel, json.dumps({"task_id": task_id, "error": error}))

    def collect_results(
        self,
        run_id: str,
        expected: int,
        timeout: float = 300.0,
    ) -> List[Dict[str, Any]]:
        """Collect results for a run via pub/sub."""
        r = self._get_redis()
        results: List[Dict[str, Any]] = []
        deadline = time.time() + timeout

        pubsub = r.pubsub()
        pubsub.subscribe(self.results_channel)

        while len(results) < expected and time.time() < deadline:
            msg = pubsub.get_message(timeout=1.0)
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                results.append(data)

        pubsub.unsubscribe(self.results_channel)
        return results

    def get_queue_size(self) -> int:
        """Get number of pending tasks."""
        r = self._get_redis()
        return r.zcard(self.queue_name)

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        r = self._get_redis()
        return {
            "pending": r.zcard(self.queue_name),
        }

    def clear(self) -> None:
        """Clear the queue."""
        r = self._get_redis()
        r.delete(self.queue_name)


@dataclass
class WorkerConfig:
    """Configuration for an evaluation worker."""
    worker_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    plugins: List[str] = field(default_factory=list)
    max_tasks: int = 0  # 0 = unlimited
    poll_interval: float = 1.0
    heartbeat_interval: float = 30.0


class EvaluationWorker:
    """A distributed evaluation worker that polls Redis for tasks.

    Each worker:
    1. Claims tasks from the Redis queue
    2. Executes them using the plugin system
    3. Publishes results back

    Usage:
        worker = EvaluationWorker(
            RedisTaskQueue(redis_url="redis://localhost:6379"),
            WorkerConfig(plugins=["mmlu", "gsm8k"]),
        )
        worker.start()  # Blocking - runs until queue empty or max_tasks reached
    """

    def __init__(
        self,
        queue: RedisTaskQueue,
        config: Optional[WorkerConfig] = None,
    ):
        self.queue = queue
        self.config = config or WorkerConfig()
        self._tasks_done = 0
        self._running = False
        self.logger = logging.getLogger(f"agent_eval.worker.{self.config.worker_id}")

    def start(self) -> None:
        """Start the worker loop. Blocks until queue empty or max_tasks reached."""
        from agent_eval.plugins.base import BasePlugin, EvalContext, PluginRegistry

        self._running = True
        self.logger.info(f"Worker {self.config.worker_id} started, plugins: {self.config.plugins}")

        # Initialize plugins
        plugin_instances: Dict[str, BasePlugin] = {}
        for pname in self.config.plugins:
            try:
                plugin = PluginRegistry.get(pname)
                plugin.setup({})
                plugin_instances[pname] = plugin
                self.logger.info(f"Loaded plugin: {pname}")
            except Exception as e:
                self.logger.error(f"Failed to load plugin '{pname}': {e}")

        context = EvalContext(
            agent_under_test=None,
            task_config={},
            metadata={"worker_id": self.config.worker_id},
        )

        while self._running:
            if self.config.max_tasks > 0 and self._tasks_done >= self.config.max_tasks:
                self.logger.info(f"Reached max_tasks={self.config.max_tasks}, stopping")
                break

            try:
                task_data = self.queue.claim_task(self.config.worker_id)
            except Exception as e:
                self.logger.error(f"Failed to claim task: {e}")
                time.sleep(self.config.poll_interval)
                continue

            if task_data is None:
                self.logger.debug("No tasks available, waiting...")
                time.sleep(self.config.poll_interval)
                continue

            task_id = task_data.get("task_id", str(uuid.uuid4()))
            plugin_name = task_data.get("_plugin", "")

            plugin = plugin_instances.get(plugin_name)
            if plugin is None:
                self.queue.fail_task(task_id, f"Unknown plugin: {plugin_name}")
                continue

            try:
                output = plugin.execute_task(task_data, context)
                result = plugin.evaluate(task_data, output, context)
                self.queue.complete_task(task_id, {
                    "score": result.score,
                    "passed": result.passed,
                    "plugin": result.plugin_name,
                    "details": result.details,
                })
                self._tasks_done += 1
                self.logger.debug(f"Task {task_id} completed: {result.score:.3f}")
            except Exception as e:
                self.queue.fail_task(task_id, str(e))
                self.logger.error(f"Task {task_id} failed: {e}")

        self.logger.info(f"Worker stopped, completed {self._tasks_done} tasks")

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False

    @property
    def tasks_completed(self) -> int:
        return self._tasks_done
