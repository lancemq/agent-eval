"""Agent Under Test abstraction for wrapping any AI agent."""

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Dict, List, Optional

from agent_eval.llm_client import LLMClient


class AgentUnderTest(ABC):
    """Abstract interface for the agent being evaluated."""

    name: str = "unnamed_agent"
    version: str = "1.0"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a single response."""
        pass

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Multi-turn conversation."""
        pass

    def act(self, state: Dict[str, Any], available_tools: List[str], goal: str) -> Dict[str, Any]:
        """Decide on an action given state and tools (for dynamic evaluation)."""
        prompt = f"""Goal: {goal}
Current State: {state}
Available Tools: {available_tools}

Decide on the next action. Return a JSON with keys: type (tool_call or finish), tool (if tool_call), params (dict of params)."""
        response = self.generate(prompt)
        return self._extract_json(response)

    @staticmethod
    def _extract_json(response: str) -> Dict[str, Any]:
        """Extract a JSON dict from response text.

        Tries fenced code blocks first, then scans for outermost { ... } pairs.
        Returns an error dict on failure so callers can distinguish parse failures
        from legitimate finish actions.
        """
        # 1. Fenced code block (```json ... ``` or ``` ... ```)
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response, re.IGNORECASE)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # 2. Scan all { ... } pairs from outermost to innermost
        starts = [m.start() for m in re.finditer(r"\{", response)]
        ends = [m.start() for m in re.finditer(r"\}", response)]
        for s in starts:
            for e in reversed(ends):
                if e <= s:
                    break
                try:
                    parsed = json.loads(response[s : e + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue

        return {"type": "error", "reason": "JSON parse failed", "raw": response}


class OpenAIAgent(AgentUnderTest):
    """Wraps an OpenAI model as the agent under test."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        system_prompt: str = "You are a helpful AI assistant.",
        temperature: float = 0.0,
        name: str = "openai_agent",
        version: str = "1.0",
        timeout: float = 60.0,
        max_retries: int = 3,
        api_key: str = None,
        base_url: str = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.name = name
        self.version = version
        self.client = LLMClient(
            model=model,
            timeout=timeout,
            max_retries=max_retries,
            api_key=api_key,
            base_url=base_url,
        )

    def generate(self, prompt: str) -> str:
        response = self.client.chat(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def chat(self, messages: List[Dict[str, str]]) -> str:
        formatted = [{"role": "system", "content": self.system_prompt}]
        formatted.extend({"role": m["role"], "content": m["content"]} for m in messages)
        response = self.client.chat(
            messages=formatted,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()


class CallableAgent(AgentUnderTest):
    """Wraps arbitrary Python callables, objects, or framework adapters."""

    GENERATE_METHODS = ("generate", "invoke", "run", "predict", "__call__")
    CHAT_METHODS = ("chat", "chat_completion", "send_messages")
    ACT_METHODS = ("act", "step", "decide_action")

    def __init__(
        self,
        generate_fn: Callable[[str], Any],
        chat_fn: Optional[Callable[[List[Dict[str, str]]], Any]] = None,
        act_fn: Optional[Callable[..., Any]] = None,
        name: str = "callable_agent",
        version: str = "1.0",
    ):
        self._generate_fn = generate_fn
        self._chat_fn = chat_fn
        self._act_fn = act_fn
        self.name = name
        self.version = version

    def generate(self, prompt: str) -> str:
        return self._coerce_text(self._generate_fn(prompt))

    def chat(self, messages: List[Dict[str, str]]) -> str:
        if self._chat_fn:
            return self._coerce_text(self._chat_fn(messages))
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt)

    def act(self, state: Dict[str, Any], available_tools: List[str], goal: str) -> Dict[str, Any]:
        if not self._act_fn:
            return super().act(state, available_tools, goal)

        action = self._act_fn(state=state, available_tools=available_tools, goal=goal)
        if isinstance(action, dict):
            return action
        if isinstance(action, str):
            return self._extract_json(action)
        return {
            "type": "error",
            "reason": f"Unsupported action response type: {type(action).__name__}",
            "raw": action,
        }

    @classmethod
    def from_module(cls, module_path: str, config: Dict[str, Any] = None) -> "CallableAgent":
        import importlib
        config = config or {}
        module_path, attr_name = module_path.split(":", 1)
        module = importlib.import_module(module_path)
        target = getattr(module, attr_name)
        instance = cls._build_target(target, config)
        return cls.from_object(instance, config=config, default_name=f"{module_path}:{attr_name}")

    @classmethod
    def from_object(
        cls,
        target: Any,
        config: Optional[Dict[str, Any]] = None,
        default_name: str = "callable_agent",
    ) -> "CallableAgent":
        """Create an adapter from an object using configurable method names."""
        config = config or {}
        method_map = config.get("methods", {})

        generate_fn = cls._resolve_method(
            target,
            method_map.get("generate"),
            cls.GENERATE_METHODS,
            required=True,
            capability="generate",
        )
        chat_fn = cls._resolve_method(
            target,
            method_map.get("chat"),
            cls.CHAT_METHODS,
            required=False,
            capability="chat",
        )
        act_fn = cls._resolve_method(
            target,
            method_map.get("act"),
            cls.ACT_METHODS,
            required=False,
            capability="act",
        )

        return cls(
            generate_fn=generate_fn,
            chat_fn=chat_fn,
            act_fn=act_fn,
            name=config.get("name", getattr(target, "name", default_name)),
            version=str(config.get("version", getattr(target, "version", "1.0"))),
        )

    @staticmethod
    def _build_target(target: Any, config: Dict[str, Any]) -> Any:
        adapter_keys = {"methods", "name", "version", "init"}
        init_config = config.get(
            "init",
            {key: value for key, value in config.items() if key not in adapter_keys},
        )
        if callable(target) and isinstance(target, type):
            return target(**init_config)
        if callable(target) and any(key in config for key in adapter_keys):
            return target(**init_config)
        return target

    @classmethod
    def _resolve_method(
        cls,
        target: Any,
        configured_name: Optional[str],
        candidates: tuple,
        required: bool,
        capability: str,
    ) -> Optional[Callable]:
        names = (configured_name,) if configured_name else candidates
        for name in names:
            if name == "__call__" and callable(target):
                return target
            method = getattr(target, name, None)
            if callable(method):
                return method
        if required:
            expected = configured_name or ", ".join(candidates)
            raise TypeError(
                f"Agent target {target!r} does not provide a callable {capability} method "
                f"(expected one of: {expected})"
            )
        return None

    @staticmethod
    def _coerce_text(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if content is not None:
            return str(content)
        if isinstance(response, dict):
            for key in ("content", "text", "response", "output"):
                if key in response:
                    return str(response[key])
            return json.dumps(response, ensure_ascii=False)
        return str(response)
