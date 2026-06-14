"""Universal agent protocol definitions.

Defines the standard interfaces that any agent can implement to be
evaluated by AgentEval. Uses structural typing (Protocol) so agents
don't need to inherit from any base class.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Protocol, runtime_checkable


class AgentCapability(str, Enum):
    """Capabilities an agent may support."""
    GENERATE = "generate"
    CHAT = "chat"
    ACT = "act"
    STREAM = "stream"
    TOOL_CALL = "tool_call"


@dataclass
class AgentResponse:
    """Standardized agent response container.

    Normalizes heterogeneous outputs (raw text, structured JSON,
    tool calls, multi-modal content) into a uniform format.
    """
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def text(self) -> str:
        return self.content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": self.tool_calls,
            "metadata": self.metadata,
        }


@dataclass
class ToolCall:
    """Represents a tool/function call made by the agent."""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    id: str = ""


@runtime_checkable
class AgentProtocol(Protocol):
    """Structural protocol for any evaluable agent.

    Any object with a compatible interface can be used - no inheritance needed.
    At minimum, an agent must support `generate(prompt) -> str`.
    """

    name: str
    version: str

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate a single-turn response from a prompt."""
        ...

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Multi-turn conversation with a message history."""
        ...

    def act(
        self,
        state: Dict[str, Any],
        available_tools: List[str],
        goal: str,
    ) -> Dict[str, Any]:
        """Decide on an action in an interactive environment."""
        ...


@runtime_checkable
class AsyncAgentProtocol(Protocol):
    """Async variant of AgentProtocol for high-throughput evaluation."""

    name: str
    version: str

    async def agenerate(self, prompt: str, **kwargs: Any) -> str: ...

    async def achat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str: ...


def detect_capabilities(obj: Any) -> List[AgentCapability]:
    """Detect which capabilities an agent object supports via duck typing."""
    caps: List[AgentCapability] = []

    method_names = {
        AgentCapability.GENERATE: ("generate", "invoke", "run", "predict", "__call__", "completion"),
        AgentCapability.CHAT: ("chat", "achat", "chat_completion", "send_messages", "conversation"),
        AgentCapability.ACT: ("act", "step", "decide_action", "next_action"),
        AgentCapability.STREAM: ("stream", "astream", "stream_chat"),
        AgentCapability.TOOL_CALL: ("tool_call", "function_call", "call_tool"),
    }

    for cap, names in method_names.items():
        if any(hasattr(obj, n) and callable(getattr(obj, n)) for n in names):
            caps.append(cap)

    return caps


def coerce_response(raw: Any) -> AgentResponse:
    """Normalize a heterogeneous agent output into an AgentResponse.

    Handles:
      - Plain strings
      - OpenAI-style objects (ChatCompletion)
      - LangChain AIMessage / dict outputs
      - Dicts with 'content' / 'output' / 'text' keys
      - Lists of content blocks
    """
    if isinstance(raw, str):
        return AgentResponse(content=raw)

    if isinstance(raw, AgentResponse):
        return raw

    # OpenAI ChatCompletion object
    if hasattr(raw, "choices") and raw.choices:
        choice = raw.choices[0]
        msg = getattr(choice, "message", None) or choice.get("message", {})
        content = getattr(msg, "content", "") if not isinstance(msg, dict) else msg.get("content", "")
        tool_calls = []
        raw_tc = getattr(msg, "tool_calls", None) if not isinstance(msg, dict) else msg.get("tool_calls")
        if raw_tc:
            for tc in raw_tc:
                fn = getattr(tc, "function", None) if not isinstance(tc, dict) else tc.get("function", {})
                name = getattr(fn, "name", "") if not isinstance(fn, dict) else fn.get("name", "")
                args_str = getattr(fn, "arguments", "{}") if not isinstance(fn, dict) else fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({"name": name, "arguments": args, "id": getattr(tc, "id", "")})
        return AgentResponse(content=content or "", tool_calls=tool_calls, raw=raw)

    # Dict with common keys
    if isinstance(raw, dict):
        content = raw.get("content") or raw.get("output") or raw.get("text") or raw.get("response") or ""
        tool_calls = raw.get("tool_calls", [])
        return AgentResponse(content=str(content), tool_calls=tool_calls, metadata=raw, raw=raw)

    # LangChain AIMessage style
    content_attr = getattr(raw, "content", None)
    if content_attr is not None:
        tool_calls_attr = getattr(raw, "tool_calls", [])
        return AgentResponse(content=str(content_attr), tool_calls=tool_calls_attr or [], raw=raw)

    # Fallback: stringify
    return AgentResponse(content=str(raw), raw=raw)


def extract_json(text: str) -> Dict[str, Any]:
    """Extract a JSON dict from model output text.

    Tries fenced code blocks first, then scans for { ... } pairs.
    Returns error dict on failure.
    """
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    starts = [m.start() for m in re.finditer(r"\{", text)]
    ends = [m.start() for m in re.finditer(r"\}", text)]
    for s in starts:
        for e in reversed(ends):
            if e <= s:
                break
            try:
                parsed = json.loads(text[s : e + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    return {"type": "error", "reason": "JSON parse failed", "raw": text}
