"""Function-based agent adapter — wraps any callable as an agent."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional

from agent_eval.orchestrator.agent import AgentUnderTest
from agent_eval.agents.protocol import coerce_response, extract_json


class FunctionAgent(AgentUnderTest):
    """Wraps a plain function or callable as an AgentUnderTest.

    This is the simplest way to integrate a custom agent:

        def my_agent(prompt: str) -> str:
            # your agent logic here
            return response

        agent = FunctionAgent(my_agent, name="my_agent")

    Supports:
      - Simple callables: fn(prompt) -> str
      - Dict-returning callables: fn(prompt) -> {"content": "..."}
      - Async callables (called synchronously)
      - Optional chat_fn override for multi-turn
    """

    def __init__(
        self,
        generate_fn: Callable,
        chat_fn: Optional[Callable] = None,
        act_fn: Optional[Callable] = None,
        name: str = "function_agent",
        version: str = "1.0",
    ):
        self._generate_fn = generate_fn
        self._chat_fn = chat_fn
        self._act_fn = act_fn
        self.name = name
        self.version = version

    def generate(self, prompt: str, **kwargs: Any) -> str:
        result = self._call_fn(self._generate_fn, prompt, **kwargs)
        return coerce_response(result).content

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        if self._chat_fn:
            result = self._call_fn(self._chat_fn, messages, **kwargs)
            return coerce_response(result).content
        # Fallback: flatten messages to a single prompt
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt, **kwargs)

    def act(
        self,
        state: Dict[str, Any],
        available_tools: List[str],
        goal: str,
    ) -> Dict[str, Any]:
        if self._act_fn:
            result = self._call_fn(self._act_fn, state=state, available_tools=available_tools, goal=goal)
            if isinstance(result, dict):
                return result
            return extract_json(str(result))
        # Fallback: prompt-based
        prompt = (
            f"Goal: {goal}\nCurrent State: {state}\n"
            f"Available Tools: {available_tools}\n\n"
            f"Return JSON: {{\"type\": \"tool_call\", \"tool\": \"...\", \"params\": {{...}}}}"
        )
        response = self.generate(prompt)
        return extract_json(response)

    @staticmethod
    def _call_fn(fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Call a function, handling async results and kwargs compatibility."""
        import asyncio

        sig = inspect.signature(fn)
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

        if accepts_kwargs:
            result = fn(*args, **kwargs)
        else:
            result = fn(*args)

        # Handle async functions
        if asyncio.iscoroutine(result):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(result)
            finally:
                loop.close()

        return result

    @classmethod
    def from_callable(cls, fn: Callable, **kwargs: Any) -> "FunctionAgent":
        """Create from a single callable that serves as generate."""
        return cls(generate_fn=fn, **kwargs)

    @classmethod
    def wrap_object(
        cls,
        obj: Any,
        name: str = "",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
    ) -> "FunctionAgent":
        """Create from any object with callable methods.

        Auto-discovers generate/chat/act methods from common names.
        """
        methods = methods or {}

        generate_names = methods.get("generate", ""), "generate", "invoke", "run", "predict", "__call__"
        chat_names = methods.get("chat", ""), "chat", "chat_completion", "send_messages"
        act_names = methods.get("act", ""), "act", "step", "decide_action"

        def find_fn(names, fallback=None):
            for n in names:
                if not n:
                    continue
                fn = getattr(obj, n, None)
                if fn and callable(fn):
                    return fn
            return fallback

        generate_fn = find_fn(generate_names)
        if generate_fn is None:
            raise TypeError(
                f"Object {type(obj).__name__} has no generate method. "
                f"Checked: {[n for n in generate_names if n]}"
            )

        return cls(
            generate_fn=generate_fn,
            chat_fn=find_fn(chat_names),
            act_fn=find_fn(act_names),
            name=name or getattr(obj, "name", "wrapped_agent"),
            version=version or getattr(obj, "version", "1.0"),
        )
