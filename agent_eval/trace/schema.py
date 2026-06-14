"""Standard trace schema for recording and replaying agent executions.

A TraceRecord captures a single complete interaction between a user and an agent,
including the full trajectory of steps (LLM calls, tool calls, thinking) and
the final output.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallSummary:
    """Summary of a single tool call within a trace."""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    success: bool = True
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolCallSummary":
        return cls(
            name=d.get("name", ""),
            arguments=d.get("arguments", {}),
            result=d.get("result"),
            success=d.get("success", True),
            duration_ms=d.get("duration_ms", 0),
        )


@dataclass
class TraceStep:
    """A single step in the agent's trajectory."""
    step_index: int
    action_type: str = ""
    action: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    state_before: Optional[Dict[str, Any]] = None
    state_after: Optional[Dict[str, Any]] = None
    duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action_type": self.action_type,
            "action": self.action,
            "result": self.result,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TraceStep":
        return cls(
            step_index=d.get("step_index", 0),
            action_type=d.get("action_type", ""),
            action=d.get("action", {}),
            result=d.get("result"),
            state_before=d.get("state_before"),
            state_after=d.get("state_after"),
            duration_ms=d.get("duration_ms", 0),
            error=d.get("error"),
        )


@dataclass
class TraceRecord:
    """Standardized record of a single agent execution trace.

    This is the universal format that all trace normalizers convert to,
    and that TaskGenerator converts into evaluation tasks.
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    agent_name: str = "unknown"
    agent_version: str = "1.0"
    trace_type: str = "single_turn"
    input: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)
    trajectory: List[TraceStep] = field(default_factory=list)
    output: str = ""
    output_structured: Optional[Dict[str, Any]] = None
    tool_calls: List[ToolCallSummary] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    source: str = "custom"
    tags: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "trace_type": self.trace_type,
            "input": self.input,
            "messages": self.messages,
            "trajectory": [s.to_dict() for s in self.trajectory],
            "output": self.output,
            "output_structured": self.output_structured,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "source": self.source,
            "tags": self.tags,
            "quality_score": self.quality_score,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TraceRecord":
        return cls(
            trace_id=d.get("trace_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", ""),
            agent_name=d.get("agent_name", "unknown"),
            agent_version=d.get("agent_version", "1.0"),
            trace_type=d.get("trace_type", "single_turn"),
            input=d.get("input", ""),
            messages=d.get("messages", []),
            trajectory=[TraceStep.from_dict(s) for s in d.get("trajectory", [])],
            output=d.get("output", ""),
            output_structured=d.get("output_structured"),
            tool_calls=[ToolCallSummary.from_dict(t) for t in d.get("tool_calls", [])],
            metadata=d.get("metadata", {}),
            success=d.get("success", True),
            error=d.get("error"),
            duration_ms=d.get("duration_ms", 0),
            source=d.get("source", "custom"),
            tags=d.get("tags", []),
            quality_score=d.get("quality_score", 0.0),
            raw=d.get("raw"),
        )

    @property
    def num_turns(self) -> int:
        return max(1, len(self.messages) // 2)

    @property
    def num_tool_calls(self) -> int:
        return len(self.tool_calls)

    @property
    def num_steps(self) -> int:
        return len(self.trajectory)

    def infer_type(self) -> str:
        """Auto-infer trace_type from content."""
        if self.trajectory and any(s.action_type == "tool_call" for s in self.trajectory):
            if len(self.trajectory) > 5:
                return "agentic"
            return "tool_use"
        if self.tool_calls:
            return "tool_use"
        if len(self.messages) > 2:
            return "multi_turn"
        return "single_turn"
