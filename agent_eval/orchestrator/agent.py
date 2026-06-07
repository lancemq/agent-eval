"""Agent Under Test abstraction for wrapping any AI agent."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


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
        import json
        import re
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"type": "finish"}


class OpenAIAgent(AgentUnderTest):
    """Wraps an OpenAI model as the agent under test."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        system_prompt: str = "You are a helpful AI assistant.",
        temperature: float = 0.0,
        name: str = "openai_agent",
        version: str = "1.0",
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.name = name
        self.version = version
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI()
            except ImportError:
                raise RuntimeError("openai library required: pip install openai")
        return self._client

    def generate(self, prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def chat(self, messages: List[Dict[str, str]]) -> str:
        client = self._get_client()
        formatted = [{"role": "system", "content": self.system_prompt}]
        formatted.extend({"role": m["role"], "content": m["content"]} for m in messages)
        response = client.chat.completions.create(
            model=self.model,
            messages=formatted,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()


class CallableAgent(AgentUnderTest):
    """Wraps a callable or class as the agent under test."""

    def __init__(self, generate_fn: callable, chat_fn: callable = None, name: str = "callable_agent", version: str = "1.0"):
        self._generate_fn = generate_fn
        self._chat_fn = chat_fn
        self.name = name
        self.version = version

    def generate(self, prompt: str) -> str:
        return self._generate_fn(prompt)

    def chat(self, messages: List[Dict[str, str]]) -> str:
        if self._chat_fn:
            return self._chat_fn(messages)
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt)

    @classmethod
    def from_module(cls, module_path: str, config: Dict[str, Any] = None) -> "CallableAgent":
        import importlib
        module_path, class_name = module_path.split(":")
        module = importlib.import_module(module_path)
        cls_obj = getattr(module, class_name)
        instance = cls_obj(**(config or {}))
        return cls(
            generate_fn=instance.generate if hasattr(instance, "generate") else instance,
            chat_fn=instance.chat if hasattr(instance, "chat") else None,
            name=getattr(instance, "name", module_path),
            version=getattr(instance, "version", "1.0"),
        )