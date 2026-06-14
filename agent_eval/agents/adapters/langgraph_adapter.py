"""LangGraph agent adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_eval.agents.adapters.base import AgentAdapter
from agent_eval.agents.protocol import coerce_response


class LangGraphAdapter(AgentAdapter):
    """Adapter for LangGraph compiled graphs and StateGraph agents.

    Supports:
      - langgraph StateGraph compiled app (app.invoke, app.stream)
      - langgraph.graph.StateGraph with messages state
      - Any object with .invoke() that takes a dict and returns a dict
    """

    GENERATE_METHODS = ("invoke", "astream", "stream", "__call__")
    CHAT_METHODS = ("invoke", "astream")
    ACT_METHODS = ("invoke",)

    def __init__(
        self,
        agent: Any,
        name: str = "langgraph_agent",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
        input_key: str = "messages",
    ):
        super().__init__(agent, name=name, version=version, methods=methods)
        self._input_key = input_key

    def generate(self, prompt: str, **kwargs: Any) -> str:
        agent = self._agent

        if hasattr(agent, "invoke"):
            input_data = {self._input_key: [{"role": "user", "content": prompt}]}
            result = agent.invoke(input_data, **{k: v for k, v in kwargs.items() if k != "config"})

            # LangGraph returns dict with 'messages' or specific output key
            if isinstance(result, dict):
                messages = result.get("messages", [])
                if messages:
                    last = messages[-1]
                    if isinstance(last, dict):
                        return last.get("content", str(result))
                    return getattr(last, "content", str(last))
                return str(result.get("output", result))

            return coerce_response(result).content

        if callable(agent):
            return coerce_response(agent(prompt)).content

        return str(agent)

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        agent = self._agent

        if hasattr(agent, "invoke"):
            input_data = {self._input_key: messages}
            result = agent.invoke(input_data)
            if isinstance(result, dict):
                out_messages = result.get("messages", [])
                if out_messages:
                    last = out_messages[-1]
                    if isinstance(last, dict):
                        return last.get("content", "")
                    return getattr(last, "content", str(last))
            return coerce_response(result).content

        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt)
