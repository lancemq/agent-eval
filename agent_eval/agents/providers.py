"""LLM provider abstraction layer.

Supports multiple LLM backends through a unified interface:
  - OpenAI (and OpenAI-compatible: vLLM, Together, Anyscale)
  - Anthropic (Claude)
  - Ollama (local models)
  - Any HTTP endpoint with OpenAI-compatible API

Environment variables are auto-detected:
  - OPENAI_API_KEY / OPENAI_BASE_URL
  - ANTHROPIC_API_KEY
  - OLLAMA_BASE_URL (default: http://localhost:11434)
"""

from __future__ import annotations

import json
import os
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    provider_name: str = "base"

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion and return the response text."""
        ...

    def chat_with_usage(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Chat with token usage info. Override for provider-specific usage."""
        text = self.chat(messages, model, temperature, max_tokens, **kwargs)
        return {"content": text, "usage": {}}


class OpenAIProvider(BaseLLMProvider):
    """OpenAI and OpenAI-compatible API provider."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff: float = 2.0,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as e:
                raise RuntimeError("openai library required: pip install openai") from e
            kwargs: Dict[str, Any] = {"timeout": self.timeout}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        client = self._get_client()
        for attempt in range(self.max_retries):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                    **kwargs,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                status = getattr(e, "status_code", None) or getattr(
                    getattr(e, "response", None), "status_code", None
                )
                if status in (401, 403):
                    raise
                if status in (429, 502, 503, 504) and attempt < self.max_retries - 1:
                    sleep_time = self.backoff * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff)
                    continue
                raise
        return ""

    def chat_with_usage(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
            **kwargs,
        )
        content = resp.choices[0].message.content.strip()
        usage = {}
        if hasattr(resp, "usage") and resp.usage:
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
                "total_tokens": getattr(resp.usage, "total_tokens", 0),
            }
        return {"content": content, "usage": usage}


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError("anthropic library required: pip install anthropic") from e
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        client = self._get_client()
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append(m)

        for attempt in range(self.max_retries):
            try:
                kwargs_send = {
                    "model": model,
                    "messages": chat_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if system_msg:
                    kwargs_send["system"] = system_msg
                resp = client.messages.create(**kwargs_send)
                return resp.content[0].text.strip()
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return ""


class OllamaProvider(BaseLLMProvider):
    """Ollama local model provider (OpenAI-compatible API)."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout
        self._inner: Optional[OpenAIProvider] = None

    def _get_provider(self) -> OpenAIProvider:
        if self._inner is None:
            self._inner = OpenAIProvider(
                api_key="ollama",
                base_url=f"{self.base_url}/v1",
                timeout=self.timeout,
            )
        return self._inner

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        return self._get_provider().chat(messages, model, temperature, max_tokens, **kwargs)


class HTTPProvider(BaseLLMProvider):
    """Generic HTTP provider for custom REST API endpoints.

    Any endpoint that accepts JSON {messages, model, ...} and returns
    {"choices": [{"message": {"content": "..."}}]} can be used.
    """

    provider_name = "http"

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        import urllib.request

        body: Dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if model:
            body["model"] = model

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.headers)

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )

        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result["choices"][0]["message"]["content"].strip()
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return ""


# --- Provider Registry ---

_PROVIDERS: Dict[str, type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "ollama": OllamaProvider,
    "http": HTTPProvider,
    "custom": HTTPProvider,
}


def get_provider(name: str, **kwargs: Any) -> BaseLLMProvider:
    """Get or create a provider by name."""
    name = name.lower().strip()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown provider: '{name}'. Available: {list(_PROVIDERS.keys())}"
        )
    return cls(**kwargs)


def register_provider(name: str, provider_class: type) -> None:
    """Register a custom LLM provider."""
    _PROVIDERS[name.lower()] = provider_class


def list_providers() -> List[str]:
    return list(_PROVIDERS.keys())


def auto_detect_provider(model: str = "") -> str:
    """Auto-detect provider from model name."""
    model_lower = model.lower()
    if model_lower.startswith(("gpt", "o1", "o3", "text-davinci", "text-embedding")):
        return "openai"
    if model_lower.startswith(("claude", "anthropic")):
        return "anthropic"
    if model_lower.startswith(("llama", "mistral", "qwen", "gemma", "phi", "deepseek")):
        return "ollama"
    return "openai"
