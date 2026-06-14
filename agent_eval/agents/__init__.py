"""Universal agent integration package.

Supports connecting ANY agent to the evaluation framework via:
  - Protocol-based duck typing (no inheritance required)
  - Framework-specific adapters (LangChain, AutoGen, CrewAI, LangGraph, etc.)
  - HTTP/REST API adapters (OpenAI-compatible, custom endpoints)
  - Provider abstraction (OpenAI, Anthropic, Ollama, Bedrock)
  - Callable/function wrappers

Quick start:
    from agent_eval.agents import AgentFactory

    # Any of these work:
    agent = AgentFactory.create("openai:gpt-4o-mini")
    agent = AgentFactory.create("anthropic:claude-sonnet-4-20250514")
    agent = AgentFactory.create("ollama:llama3")
    agent = AgentFactory.create("http://localhost:8000")
    agent = AgentFactory.create("langchain:my_module:MyAgent")
    agent = AgentFactory.create({"type": "function", "callable": my_fn})
    agent = AgentFactory.create(my_agent_instance)  # auto-wrap
"""

from agent_eval.agents.protocol import (
    AgentProtocol,
    AsyncAgentProtocol,
    AgentResponse,
    ToolCall,
    AgentCapability,
    detect_capabilities,
    coerce_response,
    extract_json,
)
from agent_eval.agents.providers import (
    BaseLLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    HTTPProvider,
    get_provider,
    register_provider,
    list_providers,
    auto_detect_provider,
)
from agent_eval.agents.adapters import (
    AgentAdapter,
    LangChainAdapter,
    AutoGenAdapter,
    CrewAIAdapter,
    LangGraphAdapter,
    HTTPAgentAdapter,
    FunctionAgent,
)
from agent_eval.agents.factory import AgentFactory, agent_type

__all__ = [
    # Protocol
    "AgentProtocol",
    "AsyncAgentProtocol",
    "AgentResponse",
    "ToolCall",
    "AgentCapability",
    "detect_capabilities",
    "coerce_response",
    "extract_json",
    # Providers
    "BaseLLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "OllamaProvider",
    "HTTPProvider",
    "get_provider",
    "register_provider",
    "list_providers",
    "auto_detect_provider",
    # Adapters
    "AgentAdapter",
    "LangChainAdapter",
    "AutoGenAdapter",
    "CrewAIAdapter",
    "LangGraphAdapter",
    "HTTPAgentAdapter",
    "FunctionAgent",
    # Factory
    "AgentFactory",
    "agent_type",
]
