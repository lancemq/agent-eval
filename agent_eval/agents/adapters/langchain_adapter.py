"""LangChain agent adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_eval.agents.adapters.base import AgentAdapter
from agent_eval.agents.protocol import coerce_response


class LangChainAdapter(AgentAdapter):
    """Adapter for LangChain agents, chains, and LLM objects.

    Supports:
      - langchain.llms.BaseLLM / langchain.chat_models.BaseChatModel
      - langchain.chains.Chain (e.g., LLMChain, ConversationChain)
      - langchain.agents.AgentExecutor
      - langchain_core.runnables.Runnable (LCEL chains)
    """

    GENERATE_METHODS = ("invoke", "predict", "__call__", "generate", "run", "apredict")
    CHAT_METHODS = ("predict_messages", "invoke", "__call__", "apredict_messages")
    ACT_METHODS = ("invoke", "plan", "take_action")

    def __init__(
        self,
        agent: Any,
        name: str = "langchain_agent",
        version: str = "1.0",
        methods: Optional[Dict[str, str]] = None,
    ):
        super().__init__(agent, name=name, version=version, methods=methods)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        agent = self._agent

        # Runnable interface (LCEL)
        if hasattr(agent, "invoke"):
            result = agent.invoke(prompt, **{k: v for k, v in kwargs.items() if k != "config"})
            return coerce_response(result).content

        # Chain interface
        if hasattr(agent, "run"):
            return str(agent.run(prompt))

        # Direct LLM call
        if hasattr(agent, "predict"):
            return str(agent.predict(prompt))

        if callable(agent):
            return coerce_response(agent(prompt)).content

        return str(agent.generate(prompt))

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        agent = self._agent

        # AgentExecutor or Runnable with message history
        if hasattr(agent, "invoke"):
            result = agent.invoke({"messages": messages}, **kwargs) if isinstance(agent.invoke(messages), dict) else agent.invoke(messages)
            return coerce_response(result).content

        # ChatModel.predict_messages
        if hasattr(agent, "predict_messages"):
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

            lc_messages = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))
            result = agent.predict_messages(lc_messages)
            return str(result.content) if hasattr(result, "content") else str(result)

        # Fallback to generate
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.generate(prompt)
