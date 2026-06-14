"""AutoGen agent adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_eval.agents.adapters.base import AgentAdapter
from agent_eval.agents.protocol import coerce_response


class AutoGenAdapter(AgentAdapter):
    """Adapter for AutoGen ConversableAgent and GroupChat.

    Supports:
      - autogen.ConversableAgent (generate_reply, a_generate_reply)
      - autogen.GroupChatManager
      - Custom agents with generate_reply
    """

    GENERATE_METHODS = ("generate_reply", "generate", "__call__")
    CHAT_METHODS = ("generate_reply", "initiate_chat", "__call__")
    ACT_METHODS = ("generate_reply",)

    def __init__(
        self,
        agent: Any,
        name: str = "autogen_agent",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
    ):
        super().__init__(agent, name=name, version=version, methods=methods)
        self._chat_history: List[Dict[str, str]] = []

    def generate(self, prompt: str, **kwargs: Any) -> str:
        agent = self._agent

        # ConversableAgent.generate_reply(messages=..., sender=...)
        if hasattr(agent, "generate_reply"):
            messages = [{"role": "user", "content": prompt}]
            result = agent.generate_reply(messages=messages, sender=None)
            return coerce_response(result).content

        if callable(agent):
            return coerce_response(agent(prompt)).content

        return str(agent)

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        agent = self._agent

        if hasattr(agent, "generate_reply"):
            result = agent.generate_reply(messages=messages, sender=None)
            return coerce_response(result).content

        if hasattr(agent, "initiate_chat"):
            last_msg = messages[-1]["content"] if messages else ""
            result = agent.initiate_chat(
                recipient=agent,
                message=last_msg,
                clear_history=False,
            )
            return coerce_response(result).content

        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt)
