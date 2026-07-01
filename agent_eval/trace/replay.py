"""Trace replay: run evaluations against pre-recorded traces without live agent calls."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_eval.orchestrator.agent import AgentUnderTest
from agent_eval.trace.schema import TraceRecord
from agent_eval.trace.store import TraceStore


class TracePlayer(AgentUnderTest):
    """Replays pre-recorded agent traces for offline evaluation.

    Wraps recorded traces as an AgentUnderTest, so any existing evaluator
    (tool_use, multi_turn) can run unchanged against recorded data.

    Usage:
        store = TraceStore(path="./traces")
        traces = {t.trace_id: t for t in store.query({"success": True})}
        player = TracePlayer(traces)
        report = orch.run_evaluation(player, ["tool_use"])
    """

    def __init__(self, traces: Dict[str, TraceRecord], name: str = "trace_player", version: str = "1.0"):
        self._traces = traces
        self._input_index: Dict[str, str] = {}
        for tid, t in traces.items():
            if t.input:
                key = t.input.strip().lower()[:200]
                self._input_index[key] = tid
        self._cursors: Dict[str, int] = {}
        self.name = name
        self.version = version

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Replay single-turn output."""
        trace = self._find_trace(prompt, kwargs.get("task_id", ""))
        if trace is None:
            return "[REPLAY_TRACE_NOT_FOUND]"
        return trace.output

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Replay multi-turn conversation output."""
        trace = self._find_trace(
            messages[-1]["content"] if messages else "",
            kwargs.get("task_id", ""),
        )
        if trace and trace.output:
            return trace.output
        return "[REPLAY_TRACE_NOT_FOUND]"

    def act(
        self,
        state: Dict[str, Any],
        available_tools: List[str],
        goal: str,
    ) -> Dict[str, Any]:
        """Replay tool-call trajectory step by step."""
        task_id = state.get("task_id", state.get("trace_id", ""))
        trace = self._find_trace(goal, task_id)
        if trace is None:
            return {"type": "finish", "result": "[REPLAY_NOT_FOUND]"}

        cursor = self._cursors.get(trace.trace_id, 0)
        if cursor < len(trace.trajectory):
            step = trace.trajectory[cursor]
            self._cursors[trace.trace_id] = cursor + 1
            action = dict(step.action) if step.action else {}
            if "type" not in action and step.action_type == "tool_call":
                action["type"] = "tool_call"
            return action if action else {"type": "finish", "result": trace.output}

        return {"type": "finish", "result": trace.output}

    def reset(self, trace_id: str = "") -> None:
        """Reset replay cursor."""
        if trace_id:
            self._cursors.pop(trace_id, None)
        else:
            self._cursors.clear()

    def _find_trace(self, input_text: str, task_id: str = "") -> Optional[TraceRecord]:
        """Find a matching trace by task_id or input text."""
        if task_id and task_id in self._traces:
            return self._traces[task_id]
        key = input_text.strip().lower()[:200]
        if key in self._input_index:
            return self._traces[self._input_index[key]]
        for trace in self._traces.values():
            if trace.input and input_text and input_text[:100].lower() in trace.input.lower():
                return trace
        return None

    @classmethod
    def from_store(cls, store: TraceStore, filters: Optional[Dict] = None) -> "TracePlayer":
        """Create a TracePlayer from a TraceStore."""
        traces = {t.trace_id: t for t in store.query(filters or {})}
        return cls(traces)
