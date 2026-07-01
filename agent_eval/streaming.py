"""Server-Sent Events (SSE) streaming for real-time evaluation progress.

Provides live progress updates during long-running evaluations.
Can be used with any web framework or CLI.

Usage:
    from agent_eval.streaming import StreamCallback, format_sse

    # In orchestrator
    callback = StreamCallback()
    orch.on_progress(callback)

    # In web handler (Flask example)
    def stream():
        for event in callback.events():
            yield format_sse(event)
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional


@dataclass
class StreamEvent:
    """A single streaming event."""
    event_type: str  # "progress", "task_complete", "task_failed", "summary", "done"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class StreamCallback:
    """Thread-safe progress callback that collects events for streaming.

    Register with orchestrator:
        cb = StreamCallback()
        orch.on_progress(cb)

    Then consume events:
        for event in cb.events(timeout=30):
            yield format_sse(event)
    """

    def __init__(self, max_queue: int = 1000):
        self._queue: queue.Queue[Optional[StreamEvent]] = queue.Queue(maxsize=max_queue)
        self._events: List[StreamEvent] = []
        self._lock = threading.Lock()
        self._closed = False

    def __call__(self, completed: int, total: int, result=None) -> None:
        """Called by orchestrator on each task completion."""
        event = StreamEvent(
            event_type="progress",
            data={
                "completed": completed,
                "total": total,
                "percent": round(completed / total * 100, 1) if total > 0 else 0,
            },
        )
        if result is not None:
            event.data["last_score"] = result.score
            event.data["last_passed"] = result.passed
            event.data["last_plugin"] = result.evaluator_name
            if result.error:
                event.data["error"] = result.error
        self._push(event)

    def _push(self, event: StreamEvent) -> None:
        """Push an event to the queue."""
        with self._lock:
            self._events.append(event)
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass  # Drop events if consumer is too slow

    def events(self, timeout: float = 30.0) -> Generator[StreamEvent, None, None]:
        """Generator that yields events as they arrive.

        Args:
            timeout: Max seconds to wait for the next event

        Yields:
            StreamEvent instances
        """
        while not self._closed:
            try:
                event = self._queue.get(timeout=timeout)
                if event is None:
                    break
                yield event
            except queue.Empty:
                break

    def get_all_events(self) -> List[StreamEvent]:
        """Get all collected events (non-blocking)."""
        with self._lock:
            return list(self._events)

    def close(self) -> None:
        """Signal end of stream."""
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def emit_summary(self, summary: Dict[str, Any]) -> None:
        """Emit a final summary event."""
        self._push(StreamEvent(event_type="summary", data=summary))

    def emit_done(self) -> None:
        """Emit a done event and close."""
        self._push(StreamEvent(event_type="done"))
        self.close()


def format_sse(event: StreamEvent) -> str:
    """Format a StreamEvent as a Server-Sent Events message.

    Usage with Flask/FastAPI:
        @app.route("/stream")
        def stream():
            def generate():
                for event in callback.events():
                    yield format_sse(event)
            return Response(generate(), mimetype="text/event-stream")
    """
    return f"event: {event.event_type}\\ndata: {event.to_json()}\\n\\n"


def format_ndjson(event: StreamEvent) -> str:
    """Format a StreamEvent as newline-delimited JSON."""
    return event.to_json() + "\n"
