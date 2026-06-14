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


class DatasetBuilder:
    """Builds versioned evaluation datasets from traces.

    Usage:
        builder = DatasetBuilder(name="prod_eval_v1")
        builder.from_traces(traces, min_quality=0.5)
        builder.save("./datasets/prod_v1.json")
    """

    def __init__(self, name: str = "unnamed", version: str = "1.0"):
        self.name = name
        self.version = version
        self.tasks: List[EvalTask] = []
        self.metadata: Dict[str, Any] = {
            "name": name,
            "version": version,
            "source_traces": [],
            "stats": {},
        }

    def from_traces(
        self,
        traces: List[TraceRecord],
        min_quality: float = 0.0,
        deduplicate: bool = True,
        filters: Optional[Dict[str, Any]] = None,
        max_tasks: int = 0,
    ) -> "DatasetBuilder":
        """Build dataset from a list of traces."""
        filtered = traces

        if filters:
            filtered = [
                t for t in filtered
                if all(getattr(t, k, None) == v for k, v in filters.items())
            ]

        if min_quality > 0:
            filtered = [t for t in filtered if t.quality_score >= min_quality]

        if deduplicate:
            filtered = self._deduplicate(filtered)

        if max_tasks > 0:
            filtered = filtered[:max_tasks]

        generator = TaskGenerator()
        self.tasks = generator.generate_batch(filtered)
        self.metadata["source_traces"] = [t.trace_id for t in filtered]
        self.metadata["stats"] = self._compute_stats()
        return self

    def from_trace_store(
        self,
        store: Any,
        min_quality: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "DatasetBuilder":
        """Build from a TraceStore."""
        traces = store.query(filters or {})
        return self.from_traces(traces, min_quality=min_quality, **kwargs)

    @staticmethod
    def _deduplicate(traces: List[TraceRecord]) -> List[TraceRecord]:
        """Remove near-duplicate traces based on input hashing."""
        seen: Dict[str, TraceRecord] = {}
        for t in traces:
            key = hashlib.sha256(t.input.encode()).hexdigest()[:16]
            if key not in seen:
                seen[key] = t
            elif t.quality_score > seen[key].quality_score:
                seen[key] = t
        return list(seen.values())

    def _compute_stats(self) -> Dict[str, Any]:
        if not self.tasks:
            return {}
        type_counts: Dict[str, int] = {}
        all_scorers: List[str] = []
        for task in self.tasks:
            type_counts[task.task_type] = type_counts.get(task.task_type, 0) + 1
            all_scorers.extend(task.scorers)
        return {
            "total_tasks": len(self.tasks),
            "by_type": type_counts,
            "unique_scorers": sorted(set(all_scorers)),
        }

    def save(self, path: str) -> str:
        """Save dataset to JSON file."""
        import json
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str) -> "DatasetBuilder":
        """Load a saved dataset."""
        import json
        with open(path) as f:
            data = json.load(f)
        builder = cls(name=data["name"], version=data.get("version", "1.0"))
        builder.tasks = [EvalTask.from_dict(t) for t in data.get("tasks", [])]
        builder.metadata = data.get("metadata", {})
        return builder

    def export_yaml(self, path: str) -> str:
        """Export as YAML config compatible with agent-eval CLI."""
        lines = [
            f"# Auto-generated dataset: {self.name} v{self.version}",
            f"# Total tasks: {len(self.tasks)}",
            "",
            "plugins:",
            "  trace_eval:",
            "    enabled: true",
            "    type: custom",
            "    test_cases:",
        ]
        for task in self.tasks:
            lines.append(f"      - id: \"{task.task_id}\"")
            lines.append(f"        type: \"{task.task_type}\"")
            lines.append(f"        input: {task.input!r}")
            if task.expected_output:
                lines.append(f"        expected: {task.expected_output!r}")
            if task.scorers:
                lines.append(f"        scorers: {task.scorers}")
        lines.append("")

        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path
