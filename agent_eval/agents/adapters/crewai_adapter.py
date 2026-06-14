"""CrewAI agent adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_eval.agents.adapters.base import AgentAdapter
from agent_eval.agents.protocol import coerce_response


class CrewAIAdapter(AgentAdapter):
    """Adapter for CrewAI Agent and Crew.

    Supports:
      - crewai.Agent (execute_task, kickoff)
      - crewai.Crew (kickoff)
      - Any object with execute_task or kickoff method
    """

    GENERATE_METHODS = ("execute_task", "kickoff", "run", "__call__")
    CHAT_METHODS = ("execute_task", "kickoff")
    ACT_METHODS = ("execute_task",)

    def __init__(
        self,
        agent: Any,
        name: str = "crewai_agent",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
        context: Optional[str] = None,
    ):
        super().__init__(agent, name=name, version=version, methods=methods)
        self._default_context = context or ""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        agent = self._agent
        context = kwargs.pop("context", self._default_context)

        if hasattr(agent, "execute_task"):
            result = agent.execute_task(task=prompt, context=context)
            return coerce_response(result).content

        if hasattr(agent, "kickoff"):
            result = agent.kickoff(inputs={"task": prompt})
            return coerce_response(result).content

        if callable(agent):
            return coerce_response(agent(prompt)).content

        return str(prompt)

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        prompt = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)
        return self.generate(prompt, **kwargs)
