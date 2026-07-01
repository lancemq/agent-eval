"""Trace normalizers: convert heterogeneous trace formats to TraceRecord."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agent_eval.trace.schema import TraceRecord, TraceStep, ToolCallSummary


class BaseTraceNormalizer(ABC):
    """Base class for trace normalizers."""

    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> TraceRecord:
        ...

    @abstractmethod
    def can_handle(self, raw: Dict[str, Any]) -> bool:
        ...


class CustomJSONNormalizer(BaseTraceNormalizer):
    """Normalizer for custom JSON formats with configurable field mapping.

    Usage:
        normalizer = CustomJSONNormalizer(field_map={
            "input": "user_query",
            "output": "agent_response",
            "messages": "conversation",
        })
        record = normalizer.normalize(raw_json_dict)
    """

    def __init__(self, field_map: Optional[Dict[str, str]] = None):
        self.field_map = field_map or {}

    def can_handle(self, raw: Dict[str, Any]) -> bool:
        return True

    def normalize(self, raw: Dict[str, Any]) -> TraceRecord:
        fm = self.field_map

        def get(key: str, default: Any = "") -> Any:
            mapped = fm.get(key, key)
            return raw.get(mapped, raw.get(key, default))

        input_text = str(get("input", ""))
        output_text = str(get("output", ""))
        messages = get("messages", [])
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        trajectory_raw = get("trajectory", [])
        trajectory = [self._parse_step(s, i) for i, s in enumerate(trajectory_raw)]

        tool_calls_raw = get("tool_calls", [])
        tool_calls = [self._parse_tool_call(tc) for tc in tool_calls_raw]

        record = TraceRecord(
            trace_id=raw.get("trace_id", str(uuid.uuid4())),
            timestamp=raw.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            agent_name=raw.get("agent_name", "unknown"),
            agent_version=raw.get("agent_version", "1.0"),
            input=input_text,
            messages=messages,
            trajectory=trajectory,
            output=output_text,
            tool_calls=tool_calls,
            metadata=raw.get("metadata", {}),
            success=raw.get("success", True),
            error=raw.get("error"),
            duration_ms=raw.get("duration_ms", 0),
            source="custom",
            tags=raw.get("tags", []),
            raw=raw,
        )
        record.trace_type = record.infer_type()
        return record

    @staticmethod
    def _parse_step(raw: Dict[str, Any], index: int) -> TraceStep:
        return TraceStep(
            step_index=raw.get("step_index", raw.get("turn", index)),
            action_type=raw.get("action_type", raw.get("type", "")),
            action=raw.get("action", raw.get("params", {})),
            result=raw.get("result", raw.get("output")),
            state_before=raw.get("state_before"),
            state_after=raw.get("state_after"),
            duration_ms=raw.get("duration_ms", 0),
            error=raw.get("error"),
        )

    @staticmethod
    def _parse_tool_call(raw: Dict[str, Any]) -> ToolCallSummary:
        return ToolCallSummary(
            name=raw.get("name", raw.get("tool", "")),
            arguments=raw.get("arguments", raw.get("params", {})),
            result=raw.get("result"),
            success=raw.get("success", True),
            duration_ms=raw.get("duration_ms", 0),
        )


class SelfEvalNormalizer(BaseTraceNormalizer):
    """Converts AgentEval's own EvalResult into a TraceRecord.

    Enables building datasets from previous evaluation runs.
    """

    def can_handle(self, raw: Dict[str, Any]) -> bool:
        return "evaluator_name" in raw and "evaluation_type" in raw

    def normalize(self, raw: Dict[str, Any]) -> TraceRecord:
        details = raw.get("details", {})
        task_data = details.get("task", details.get("task_data", {}))

        messages: List[Dict[str, str]] = []
        conversation = details.get("conversation", [])
        if conversation:
            messages = conversation
        elif task_data.get("prompt"):
            messages = [{"role": "user", "content": task_data["prompt"]}]

        trajectory_raw = details.get("trajectory", [])
        trajectory = [
            TraceStep(
                step_index=s.get("turn", i),
                action_type=s.get("action", {}).get("type", ""),
                action=s.get("action", {}),
                result=s.get("result"),
                state_before=s.get("state_before"),
                state_after=s.get("state_after"),
            )
            for i, s in enumerate(trajectory_raw)
        ]

        tool_calls_raw = details.get("tool_calls", [])
        tool_calls = [
            ToolCallSummary(
                name=tc.get("name", tc.get("tool", "")),
                arguments=tc.get("arguments", tc.get("params", {})),
                result=tc.get("result"),
            )
            for tc in tool_calls_raw
        ]

        input_text = task_data.get("prompt", task_data.get("goal", task_data.get("instruction", "")))
        output_text = str(details.get("output", details.get("response", "")))

        record = TraceRecord(
            trace_id=raw.get("task_id", str(uuid.uuid4())),
            timestamp=raw.get("timestamp", ""),
            agent_name=raw.get("agent_name", "unknown"),
            trace_type=record_infer_type(trajectory, messages, tool_calls),
            input=input_text,
            messages=messages,
            trajectory=trajectory,
            output=output_text,
            tool_calls=tool_calls,
            metadata={
                "evaluator_name": raw.get("evaluator_name", ""),
                "evaluation_type": raw.get("evaluation_type", ""),
                "score": raw.get("score", 0),
                "passed": raw.get("passed", False),
                "execution_time_ms": raw.get("execution_time_ms", 0),
                "dimension_scores": raw.get("dimension_scores", {}),
            },
            success=raw.get("passed", False),
            error=raw.get("error"),
            duration_ms=raw.get("execution_time_ms", 0),
            source="self_eval",
            tags=[raw.get("evaluator_name", "")] if raw.get("evaluator_name") else [],
            quality_score=float(raw.get("score", 0)),
        )
        return record


class OpenTelemetryNormalizer(BaseTraceNormalizer):
    """Converts OpenTelemetry span data to TraceRecord.

    Expects a flat list of spans with parent_span_id relationships.
    """

    def can_handle(self, raw: Dict[str, Any]) -> bool:
        return "spans" in raw or (
            isinstance(raw, list) and all("span_id" in s for s in raw[:3])
        )

    def normalize(self, raw: Dict[str, Any]) -> TraceRecord:
        spans = raw.get("spans", raw if isinstance(raw, list) else [])

        root_spans = [s for s in spans if not s.get("parent_span_id")]
        root = root_spans[0] if root_spans else (spans[0] if spans else {})

        attrs = root.get("attributes", {})
        messages: List[Dict[str, str]] = []
        trajectory: List[TraceStep] = []
        tool_calls_list: List[ToolCallSummary] = []
        input_text = ""
        output_text = ""

        for i, span in enumerate(spans):
            sa = span.get("attributes", {})
            span_name = span.get("name", "")
            duration = 0
            if span.get("start_time") and span.get("end_time"):
                duration = int(span["end_time"] - span["start_time"])

            if sa.get("llm.system") or "llm" in span_name.lower():
                if sa.get("llm.prompts"):
                    input_text = str(sa["llm.prompts"])
                if sa.get("llm.completions"):
                    output_text = str(sa["llm.completions"])
                trajectory.append(TraceStep(
                    step_index=i, action_type="llm_call",
                    action={"prompt": input_text[:500]},
                    result=output_text[:500],
                    duration_ms=duration,
                ))
            elif sa.get("tool.name") or "tool" in span_name.lower():
                tool_name = sa.get("tool.name", span_name)
                tool_args = sa.get("tool.arguments", {})
                tool_result = sa.get("tool.result")
                tool_calls_list.append(ToolCallSummary(
                    name=tool_name, arguments=tool_args,
                    result=tool_result, duration_ms=duration,
                ))
                trajectory.append(TraceStep(
                    step_index=i, action_type="tool_call",
                    action={"tool": tool_name, "params": tool_args},
                    result=tool_result, duration_ms=duration,
                ))

        if not input_text and messages:
            input_text = messages[0].get("content", "") if messages else ""

        record = TraceRecord(
            trace_id=root.get("trace_id", str(uuid.uuid4())),
            timestamp=root.get("start_time", ""),
            agent_name=attrs.get("agent.name", "otel_agent"),
            input=input_text,
            messages=messages,
            trajectory=trajectory,
            output=output_text,
            tool_calls=tool_calls_list,
            metadata={"span_count": len(spans)},
            success=root.get("status", {}).get("code") != "ERROR",
            duration_ms=sum(s.duration_ms for s in trajectory),
            source="opentelemetry",
            raw=raw,
        )
        record.trace_type = record.infer_type()
        return record


class LangSmithNormalizer(BaseTraceNormalizer):
    """Converts LangSmith run data to TraceRecord."""

    def can_handle(self, raw: Dict[str, Any]) -> bool:
        return "runs" in raw or "child_runs" in raw

    def normalize(self, raw: Dict[str, Any]) -> TraceRecord:
        child_runs = raw.get("child_runs", raw.get("runs", []))

        input_text = str(raw.get("inputs", {}).get("input", raw.get("inputs", {}).get("question", "")))
        output_text = str(raw.get("outputs", {}).get("output", raw.get("outputs", {}).get("result", "")))

        trajectory: List[TraceStep] = []
        tool_calls_list: List[ToolCallSummary] = []

        for i, run in enumerate(child_runs):
            run_type = run.get("run_type", "")
            if run_type == "tool":
                tool_name = run.get("name", "")
                tool_args = run.get("inputs", {})
                tool_result = run.get("outputs", {}).get("output")
                tool_calls_list.append(ToolCallSummary(
                    name=tool_name, arguments=tool_args, result=tool_result,
                ))
                trajectory.append(TraceStep(
                    step_index=i, action_type="tool_call",
                    action={"tool": tool_name, "params": tool_args},
                    result=tool_result,
                ))
            elif run_type in ("llm", "chain"):
                trajectory.append(TraceStep(
                    step_index=i, action_type="llm_call",
                    action={"name": run.get("name", "")},
                    result=run.get("outputs"),
                ))

        messages = [{"role": "user", "content": input_text}] if input_text else []
        if output_text:
            messages.append({"role": "assistant", "content": output_text})

        record = TraceRecord(
            trace_id=raw.get("id", str(uuid.uuid4())),
            timestamp=raw.get("start_time", ""),
            agent_name=raw.get("session_name", "langsmith_agent"),
            input=input_text,
            messages=messages,
            trajectory=trajectory,
            output=output_text,
            tool_calls=tool_calls_list,
            metadata={"run_type": raw.get("run_type", "")},
            success=raw.get("status", "") == "S" or raw.get("error") is None,
            error=raw.get("error"),
            source="langsmith",
            raw=raw,
        )
        record.trace_type = record.infer_type()
        return record


def record_infer_type(trajectory: List[TraceStep], messages: List[Dict], tool_calls: List[ToolCallSummary]) -> str:
    if trajectory and any(s.action_type == "tool_call" for s in trajectory):
        return "agentic" if len(trajectory) > 5 else "tool_use"
    return "multi_turn" if len(messages) > 2 else "single_turn"


_NORMALIZERS: Dict[str, type] = {
    "custom": CustomJSONNormalizer,
    "self_eval": SelfEvalNormalizer,
    "opentelemetry": OpenTelemetryNormalizer,
    "otel": OpenTelemetryNormalizer,
    "langsmith": LangSmithNormalizer,
}


def get_normalizer(source: str, **kwargs: Any) -> BaseTraceNormalizer:
    """Get a normalizer by source name."""
    cls = _NORMALIZERS.get(source.lower())
    if cls is None:
        raise ValueError(f"Unknown source: '{source}'. Available: {list(_NORMALIZERS.keys())}")
    return cls(**kwargs)


def auto_detect_normalizer(raw: Dict[str, Any]) -> BaseTraceNormalizer:
    """Auto-detect the right normalizer for raw data."""
    for cls in [OpenTelemetryNormalizer, LangSmithNormalizer, SelfEvalNormalizer, CustomJSONNormalizer]:
        normalizer = cls()
        try:
            if normalizer.can_handle(raw):
                return normalizer
        except Exception:
            continue
    return CustomJSONNormalizer()


def list_normalizers() -> List[str]:
    return list(_NORMALIZERS.keys())
