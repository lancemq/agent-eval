"""Base adapter class for framework-specific agent wrappers."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent_eval.agents.protocol import (
    coerce_response,
    detect_capabilities,
    extract_json,
)
from agent_eval.orchestrator.agent import AgentUnderTest


class AgentAdapter(AgentUnderTest):
    """Base class for framework-specific agent adapters.

    Subclasses wrap a framework agent instance and translate calls
    between the AgentUnderTest interface and the framework's native API.

    Override `generate`, `chat`, and/or `act` as needed.
    """

    # Common method name candidates for auto-discovery
    GENERATE_METHODS: Tuple[str, ...] = ("generate", "invoke", "run", "predict", "__call__", "completion", "achat_completion")
    CHAT_METHODS: Tuple[str, ...] = ("chat", "achat", "chat_completion", "send_messages", "conversation", "stream_chat")
    ACT_METHODS: Tuple[str, ...] = ("act", "step", "decide_action", "next_action", "think", "plan")

    def __init__(
        self,
        agent: Any,
        name: str = "adapted_agent",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
    ):
        self._agent = agent
        self.name = name
        self.version = version
        self._method_map = methods or {}
        self._capabilities = detect_capabilities(agent)

    @property
    def agent(self) -> Any:
        return self._agent

    @property
    def capabilities(self) -> List[str]:
        return [c.value for c in self._capabilities]

    def _resolve_method(self, kind: str, candidates: Tuple[str, ...]) -> Callable:
        """Find a callable on the wrapped agent by checking explicit map, then candidates."""
        # Check explicit method map first
        mapped = self._method_map.get(kind)
        if mapped:
            fn = getattr(self._agent, mapped, None)
            if fn and callable(fn):
                return fn
            raise TypeError(
                f"Mapped method '{mapped}' for '{kind}' not found on {type(self._agent).__name__}"
            )

        # Check candidates
        for name in candidates:
            fn = getattr(self._agent, name, None)
            if fn and callable(fn):
                return fn

        raise TypeError(
            f"No suitable method for '{kind}' on {type(self._agent).__name__}. "
            f"Checked: {candidates}. "
            f"Pass methods={{'{kind}': 'method_name'}} to specify."
        )

    @staticmethod
    def _to_text(raw: Any) -> str:
        return coerce_response(raw).content

    def generate(self, prompt: str, **kwargs: Any) -> str:
        fn = self._resolve_method("generate", self.GENERATE_METHODS)
        result = fn(prompt, **kwargs) if _accepts_kwargs(fn) else fn(prompt)
        return self._to_text(result)

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        try:
            fn = self._resolve_method("chat", self.CHAT_METHODS)
            result = fn(messages, **kwargs) if _accepts_kwargs(fn) else fn(messages)
            return self._to_text(result)
        except TypeError:
            # Fallback: use generate with formatted messages
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            return self.generate(prompt)

    def act(
        self,
        state: Dict[str, Any],
        available_tools: List[str],
        goal: str,
    ) -> Dict[str, Any]:
        try:
            fn = self._resolve_method("act", self.ACT_METHODS)
            result = fn(state=state, available_tools=available_tools, goal=goal)
            if isinstance(result, dict):
                return result
            return extract_json(str(result))
        except TypeError:
            # Fallback: prompt-based action selection
            prompt = (
                f"Goal: {goal}\nCurrent State: {json.dumps(state)}\n"
                f"Available Tools: {available_tools}\n\n"
                f"Decide on the next action. Return JSON: "
                f'{{"type": "tool_call", "tool": "...", "params": {{...}}}}'
                f' or {{"type": "finish", "result": "..."}}'
            )
            response = self.generate(prompt)
            return extract_json(response)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} wraps={type(self._agent).__name__}>"


def _accepts_kwargs(fn: Callable) -> bool:
    """Check if a function accepts **kwargs."""
    try:
        sig = inspect.signature(fn)
        return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    except (ValueError, TypeError):
        return False
