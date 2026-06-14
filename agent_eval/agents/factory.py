"""Universal agent factory.

Creates the right agent adapter from a specification string, dict, or object.
Supports auto-detection and manual selection of agent type.

Specification formats:
  String specs:
    "openai:gpt-4o-mini"          → OpenAIProvider agent
    "anthropic:claude-sonnet-4-20250514" → AnthropicProvider agent
    "ollama:llama3"               → OllamaProvider agent
    "http:http://localhost:8000"  → HTTPAgentAdapter
    "module:path/to/agent:Class"  → Import and wrap
    "langchain:module:Class"      → LangChain adapter
    "autogen:module:Class"        → AutoGen adapter
    "crewai:module:Class"         → CrewAI adapter
    "langgraph:module:Class"      → LangGraph adapter
    "agent.module.path:ClassName" → CallableAgent (auto-detect)

  Dict specs:
    {"type": "openai", "model": "gpt-4o", "system_prompt": "..."}
    {"type": "anthropic", "model": "claude-sonnet-4-20250514"}
    {"type": "http", "base_url": "http://localhost:8000"}
    {"type": "langchain", "module": "my_module", "class": "MyAgent"}
    {"type": "function", "callable": my_fn}
    {"type": "callable", "object": my_agent_instance}

  Object specs:
    Any object with generate/invoke/run method → auto-wrapped
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Union

from agent_eval.orchestrator.agent import AgentUnderTest, OpenAIAgent
from agent_eval.agents.adapters.langchain_adapter import LangChainAdapter
from agent_eval.agents.adapters.autogen_adapter import AutoGenAdapter
from agent_eval.agents.adapters.crewai_adapter import CrewAIAdapter
from agent_eval.agents.adapters.langgraph_adapter import LangGraphAdapter
from agent_eval.agents.adapters.http_adapter import HTTPAgentAdapter
from agent_eval.agents.adapters.function_adapter import FunctionAgent


# Registry of adapter types
_ADAPTERS: Dict[str, type] = {
    "openai": OpenAIAgent,
    "anthropic": None,  # lazy
    "ollama": None,     # lazy
    "http": HTTPAgentAdapter,
    "langchain": LangChainAdapter,
    "autogen": AutoGenAdapter,
    "crewai": CrewAIAdapter,
    "langgraph": LangGraphAdapter,
    "function": FunctionAgent,
    "callable": None,   # uses FunctionAgent.wrap_object
}

# Provider-based specs
_PROVIDER_SPECS = {"openai", "anthropic", "ollama", "claude"}


class AgentFactory:
    """Universal factory for creating agents from specifications."""

    _registry: Dict[str, type] = _ADAPTERS

    @classmethod
    def register(cls, name: str, adapter_class: type) -> None:
        """Register a custom adapter type."""
        cls._registry[name] = adapter_class

    @classmethod
    def create(
        cls,
        spec: Union[str, Dict[str, Any], Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentUnderTest:
        """Create an agent from a specification.

        Args:
            spec: Agent specification (string, dict, or object)
            config: Optional configuration dict (merged with spec for dict-type)

        Returns:
            An AgentUnderTest instance ready for evaluation.
        """
        config = config or {}

        # Already an AgentUnderTest
        if isinstance(spec, AgentUnderTest):
            return spec

        # String spec: parse prefix
        if isinstance(spec, str):
            return cls._from_string(spec, config)

        # Dict spec: use "type" key
        if isinstance(spec, dict):
            return cls._from_dict(spec, config)

        # Raw object: auto-wrap
        return cls._from_object(spec, config)

    @classmethod
    def _from_string(cls, spec: str, config: Dict[str, Any]) -> AgentUnderTest:
        """Parse string specification."""
        # Known provider prefixes
        if spec.startswith("openai:"):
            model = spec.split(":", 1)[1]
            return OpenAIAgent(model=model, **config)

        if spec.startswith(("anthropic:", "claude:")):
            return cls._create_provider_agent("anthropic", spec.split(":", 1)[1], config)

        if spec.startswith("ollama:"):
            return cls._create_provider_agent("ollama", spec.split(":", 1)[1], config)

        if spec.startswith("http://") or spec.startswith("https://"):
            return HTTPAgentAdapter(base_url=spec, **config)

        if spec.startswith("http:"):
            return HTTPAgentAdapter(base_url=spec.split(":", 1)[1], **config)

        # Framework prefixes: "langchain:module:Class"
        for prefix in ("langchain:", "autogen:", "crewai:", "langgraph:"):
            if spec.startswith(prefix):
                framework = prefix.rstrip(":")
                module_class = spec[len(prefix):]
                return cls._create_framework_agent(framework, module_class, config)

        # "module:Class" → import and auto-detect
        if ":" in spec:
            return cls._create_from_module(spec, config)

        raise ValueError(
            f"Cannot parse agent spec: '{spec}'. "
            f"Use 'provider:model', 'http://url', 'framework:module:Class', "
            f"or 'module:Class'."
        )

    @classmethod
    def _from_dict(cls, spec: Dict[str, Any], config: Dict[str, Any]) -> AgentUnderTest:
        """Create from dict specification."""
        merged = {**spec, **config}
        agent_type = merged.pop("type", "").lower().strip()

        if not agent_type:
            raise ValueError(f"Agent dict spec missing 'type' key: {spec}")

        # Provider-based
        if agent_type in _PROVIDER_SPECS:
            model = merged.pop("model", "")
            return cls._create_provider_agent(agent_type, model, merged)

        # HTTP
        if agent_type in ("http", "rest", "api"):
            base_url = merged.pop("base_url", merged.pop("url", ""))
            if not base_url:
                raise ValueError("HTTP agent requires 'base_url'")
            return HTTPAgentAdapter(base_url=base_url, **merged)

        # Framework adapters
        if agent_type in ("langchain", "autogen", "crewai", "langgraph"):
            module = merged.pop("module", "")
            class_name = merged.pop("class", merged.pop("class_name", ""))
            if module and class_name:
                obj = cls._import_and_instantiate(f"{module}:{class_name}", merged)
                adapter_cls = cls._registry.get(agent_type)
                if adapter_cls:
                    return adapter_cls(obj, **merged)
            # If object was passed directly
            obj = merged.pop("object", merged.pop("agent", None))
            if obj:
                adapter_cls = cls._registry.get(agent_type)
                if adapter_cls:
                    return adapter_cls(obj, **merged)
            raise ValueError(f"{agent_type} adapter requires 'module'+'class' or 'object'")

        # Function
        if agent_type == "function":
            fn = merged.pop("callable", merged.pop("fn", None))
            if fn and callable(fn):
                return FunctionAgent(generate_fn=fn, **merged)
            raise ValueError("Function agent requires 'callable' key")

        # Callable / object wrapping
        if agent_type in ("callable", "object", "wrap"):
            obj = merged.pop("object", merged.pop("agent", None))
            if obj:
                return FunctionAgent.wrap_object(obj, **merged)
            raise ValueError("Callable agent requires 'object' key")

        # Custom registered adapter
        if agent_type in cls._registry and cls._registry[agent_type]:
            adapter_cls = cls._registry[agent_type]
            return adapter_cls(**merged)

        raise ValueError(
            f"Unknown agent type: '{agent_type}'. "
            f"Available: {cls.list_types()}"
        )

    @classmethod
    def _from_object(cls, obj: Any, config: Dict[str, Any]) -> AgentUnderTest:
        """Auto-wrap a raw object as an agent."""
        if hasattr(obj, "generate") or hasattr(obj, "invoke") or callable(obj):
            return FunctionAgent.wrap_object(obj, **config)
        raise ValueError(
            f"Object {type(obj).__name__} has no agent methods "
            f"(generate/invoke/__call__). Cannot wrap."
        )

    @classmethod
    def _create_provider_agent(
        cls, provider: str, model: str, config: Dict[str, Any]
    ) -> AgentUnderTest:
        """Create an agent backed by an LLM provider."""
        from agent_eval.agents.providers import get_provider

        provider_inst = get_provider(provider, **{
            k: v for k, v in config.items()
            if k in ("api_key", "base_url", "timeout", "max_retries", "headers")
        })

        system_prompt = config.get("system_prompt", "You are a helpful AI assistant.")
        temperature = config.get("temperature", 0.0)
        name = config.get("name", f"{provider}_agent")

        class ProviderAgent(AgentUnderTest):
            def __init__(self_inner):
                self_inner.name = name
                self_inner.version = "1.0"

            def generate(self_inner, prompt: str, **kw: Any) -> str:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]
                return provider_inst.chat(
                    messages,
                    model=model,
                    temperature=kw.get("temperature", temperature),
                    max_tokens=kw.get("max_tokens", 1000),
                )

            def chat(self_inner, messages: List[Dict[str, str]], **kw: Any) -> str:
                formatted = [{"role": "system", "content": system_prompt}]
                formatted.extend(messages)
                return provider_inst.chat(
                    formatted,
                    model=model,
                    temperature=kw.get("temperature", temperature),
                    max_tokens=kw.get("max_tokens", 1000),
                )

        return ProviderAgent()

    @classmethod
    def _create_framework_agent(
        cls, framework: str, module_class: str, config: Dict[str, Any]
    ) -> AgentUnderTest:
        """Create a framework-specific adapter from module:Class spec."""
        obj = cls._import_and_instantiate(module_class, config)
        adapter_cls = cls._registry.get(framework)
        if adapter_cls is None:
            raise ValueError(f"No adapter registered for framework: '{framework}'")
        return adapter_cls(obj, **{k: v for k, v in config.items() if k not in ("init",)})

    @classmethod
    def _create_from_module(cls, spec: str, config: Dict[str, Any]) -> AgentUnderTest:
        """Import module:Class, instantiate, and auto-wrap."""
        obj = cls._import_and_instantiate(spec, config)

        # Check if it's a known framework object
        class_name = type(obj).__module__ + "." + type(obj).__name__
        if "langchain" in class_name.lower():
            return LangChainAdapter(obj, **config)
        if "autogen" in class_name.lower():
            return AutoGenAdapter(obj, **config)
        if "crewai" in class_name.lower():
            return CrewAIAdapter(obj, **config)
        if "langgraph" in class_name.lower():
            return LangGraphAdapter(obj, **config)

        # Generic auto-wrap
        return FunctionAgent.wrap_object(obj, **config)

    @staticmethod
    def _import_and_instantiate(spec: str, config: Dict[str, Any]) -> Any:
        """Import 'module:attr' and instantiate if it's a class."""
        if ":" not in spec:
            raise ValueError(f"Module spec must be 'module:attr', got: '{spec}'")
        module_path, attr_name = spec.split(":", 1)
        module = importlib.import_module(module_path)
        target = getattr(module, attr_name)

        # If it's a class, instantiate with config
        if isinstance(target, type):
            init_config = config.get("init", {})
            return target(**init_config)

        # If it's a factory function, call it
        if callable(target) and not hasattr(target, "generate"):
            return target(**config.get("init", {}))

        # It's an instance
        return target

    @classmethod
    def list_types(cls) -> List[str]:
        """List all registered agent types."""
        all_types = {t for t, adapter in cls._registry.items() if adapter is not None}
        all_types.update(_PROVIDER_SPECS)
        return sorted(all_types)


def agent_type(name: str):
    """Decorator to register a custom agent adapter type.

    Usage:
        @agent_type("my_framework")
        class MyFrameworkAdapter(AgentAdapter):
            ...
    """
    def decorator(cls: type) -> type:
        AgentFactory.register(name, cls)
        return cls
    return decorator
