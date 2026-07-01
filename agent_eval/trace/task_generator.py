"""Generate evaluation tasks from trace records."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from agent_eval.trace.schema import TraceRecord


class EvalTask:
    """An evaluation task generated from a trace."""

    def __init__(
        self,
        task_id: str = "",
        task_type: str = "single_turn",
        input: str = "",
        expected_output: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
        trajectory: Optional[List] = None,
        available_tools: Optional[List[str]] = None,
        success_criteria: Optional[Dict[str, Any]] = None,
        scorers: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.input = input
        self.expected_output = expected_output
        self.messages = messages or []
        self.trajectory = trajectory or []
        self.available_tools = available_tools or []
        self.success_criteria = success_criteria or {}
        self.scorers = scorers or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "input": self.input,
            "expected_output": self.expected_output,
            "messages": self.messages,
            "trajectory": self.trajectory,
            "available_tools": self.available_tools,
            "success_criteria": self.success_criteria,
            "scorers": self.scorers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvalTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__init__.__code__.co_varnames})


class TaskGenerator:
    """Converts TraceRecords into evaluation tasks.

    Automatically dispatches by trace type and selects appropriate scorers.
    """

    SCORER_MAP = {
        "single_turn": ["answer_correctness", "answer_relevancy", "fluency"],
        "multi_turn": ["conversation_quality", "coherence", "role_adherence"],
        "tool_use": ["tool_call_correctness", "task_efficiency", "task_completion"],
        "agentic": [
            "task_completion", "tool_call_correctness",
            "task_efficiency", "coherence",
        ],
    }

    def generate(self, trace: TraceRecord) -> EvalTask:
        """Generate a single eval task from a trace."""
        dispatch = {
            "single_turn": self._from_single_turn,
            "multi_turn": self._from_multi_turn,
            "tool_use": self._from_tool_use,
            "agentic": self._from_agentic,
        }
        handler = dispatch.get(trace.trace_type, self._from_single_turn)
        task = handler(trace)
        if not task.scorers:
            task.scorers = self.SCORER_MAP.get(trace.trace_type, self.SCORER_MAP["single_turn"])
        return task

    def generate_batch(self, traces: List[TraceRecord]) -> List[EvalTask]:
        """Generate tasks from multiple traces."""
        return [self.generate(t) for t in traces]

    def _from_single_turn(self, trace: TraceRecord) -> EvalTask:
        return EvalTask(
            task_id=trace.trace_id,
            task_type="single_turn",
            input=trace.input,
            expected_output=trace.output,
            messages=trace.messages,
            metadata=self._extract_metadata(trace),
            scorers=self.SCORER_MAP["single_turn"][:],
        )

    def _from_multi_turn(self, trace: TraceRecord) -> EvalTask:
        return EvalTask(
            task_id=trace.trace_id,
            task_type="multi_turn",
            input=trace.input,
            expected_output=trace.output,
            messages=trace.messages,
            metadata=self._extract_metadata(trace),
            scorers=self.SCORER_MAP["multi_turn"][:],
        )

    def _from_tool_use(self, trace: TraceRecord) -> EvalTask:
        tools_used = list({tc.name for tc in trace.tool_calls})
        successful_tools = [tc.name for tc in trace.tool_calls if tc.success]
        trajectory = [s.to_dict() for s in trace.trajectory]

        return EvalTask(
            task_id=trace.trace_id,
            task_type="tool_use",
            input=trace.input,
            expected_output=trace.output,
            available_tools=tools_used,
            trajectory=trajectory,
            success_criteria={
                "must_call": successful_tools,
                "expected_result": trace.output,
                "max_turns": max(len(trajectory) + 2, 10),
            },
            metadata=self._extract_metadata(trace),
            scorers=self.SCORER_MAP["tool_use"][:],
        )

    def _from_agentic(self, trace: TraceRecord) -> EvalTask:
        tools_used = list({tc.name for tc in trace.tool_calls})
        trajectory = [s.to_dict() for s in trace.trajectory]

        return EvalTask(
            task_id=trace.trace_id,
            task_type="agentic",
            input=trace.input,
            expected_output=trace.output,
            available_tools=tools_used,
            trajectory=trajectory,
            success_criteria={
                "must_call": [tc.name for tc in trace.tool_calls],
                "expected_result": trace.output,
                "max_turns": max(len(trajectory) * 2, 10),
            },
            metadata=self._extract_metadata(trace),
            scorers=self.SCORER_MAP["agentic"][:],
        )

    @staticmethod
    def _extract_metadata(trace: TraceRecord) -> Dict[str, Any]:
        return {
            "source_trace": trace.trace_id,
            "trace_type": trace.trace_type,
            "original_duration_ms": trace.duration_ms,
            "original_success": trace.success,
            "num_tool_calls": trace.num_tool_calls,
            "num_turns": trace.num_turns,
            "tags": trace.tags,
        }

