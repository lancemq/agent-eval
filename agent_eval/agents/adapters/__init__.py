"""Framework-specific agent adapters.

Each adapter wraps a specific agent framework (LangChain, AutoGen, etc.)
and exposes a unified interface compatible with AgentUnderTest.
"""

from agent_eval.agents.adapters.base import AgentAdapter
from agent_eval.agents.adapters.langchain_adapter import LangChainAdapter
from agent_eval.agents.adapters.autogen_adapter import AutoGenAdapter
from agent_eval.agents.adapters.crewai_adapter import CrewAIAdapter
from agent_eval.agents.adapters.langgraph_adapter import LangGraphAdapter
from agent_eval.agents.adapters.http_adapter import HTTPAgentAdapter
from agent_eval.agents.adapters.function_adapter import FunctionAgent

__all__ = [
    "AgentAdapter",
    "LangChainAdapter",
    "AutoGenAdapter",
    "CrewAIAdapter",
    "LangGraphAdapter",
    "HTTPAgentAdapter",
    "FunctionAgent",
]
