"""Task queue for distributing evaluation tasks."""

import time
import uuid
import heapq
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A single evaluation task."""
    task_id: str
    data: Dict[str, Any]
    plugin_name: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    retries: int = 0
    max_retries: int = 3

    def __lt__(self, other):
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at


class TaskQueue:
    """Priority-based task queue."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._queue: List[Task] = []
        self._tasks: Dict[str, Task] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

    def enqueue(self, task_data: Dict[str, Any], plugin_name: str = "", priority: TaskPriority = TaskPriority.NORMAL) -> str:
        task_id = task_data.get("task_id", str(uuid.uuid4()))
        if task_id in self._tasks:
            raise ValueError(f"Task {task_id} already exists")

        task = Task(
            task_id=task_id,
            data=task_data,
            plugin_name=plugin_name,
            priority=priority,
        )
        self._tasks[task_id] = task
        heapq.heappush(self._queue, task)
        self._trigger_callbacks("enqueue", task)
        return task_id

    def enqueue_batch(self, tasks: List[Dict[str, Any]], priority: str = "normal") -> List[str]:
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "critical": TaskPriority.CRITICAL,
        }
        p = priority_map.get(priority, TaskPriority.NORMAL)
        task_ids = []
        for task in tasks:
            plugin_name = task.pop("_plugin", "")
            task_id = self.enqueue(task, plugin_name=plugin_name, priority=p)
            task_ids.append(task_id)
        return task_ids

    def dequeue(self) -> Optional[Task]:
        while self._queue:
            task = heapq.heappop(self._queue)
            if task.status == TaskStatus.CANCELLED:
                continue
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self._trigger_callbacks("dequeue", task)
            return task
        return None

    def complete(self, task_id: str, result: Any = None) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.result = result
            self._trigger_callbacks("complete", task)

    def fail(self, task_id: str, error: str = "") -> None:
        task = self._tasks.get(task_id)
        if task:
            if task.retries < task.max_retries:
                task.retries += 1
                task.status = TaskStatus.PENDING
                heapq.heappush(self._queue, task)
            else:
                task.status = TaskStatus.FAILED
                task.error = error
                self._trigger_callbacks("fail", task)

    def cancel(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            self._trigger_callbacks("cancel", task)

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_pending(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def get_running(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def get_completed(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]

    def get_failed(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.FAILED]

    def size(self) -> int:
        return len(self._queue)

    def total(self) -> int:
        return len(self._tasks)

    def progress(self) -> Dict[str, int]:
        return {
            "total": self.total(),
            "pending": len(self.get_pending()),
            "running": len(self.get_running()),
            "completed": len(self.get_completed()),
            "failed": len(self.get_failed()),
        }

    def on(self, event: str, callback: Callable) -> None:
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _trigger_callbacks(self, event: str, task: Task) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(task)
            except Exception:
                pass

    def clear(self) -> None:
        self._queue.clear()
        self._tasks.clear()