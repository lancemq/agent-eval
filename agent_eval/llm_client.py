"""Unified LLM client with retry, timeout and rate-limit handling."""

import time
from typing import Any, Dict, List, Optional


class LLMClient:
    """Wrapper around OpenAI client with configurable retry and timeout."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff: float = 2.0,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.api_key = api_key
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
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
        temperature: float = 0.0,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> Any:
        """Send a chat completion request with retry logic.

        Retries on 429, 502, 503, 504 with exponential backoff.
        Raises immediately on 401, 403.
        """
        client = self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                return client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                status_code = self._extract_status_code(e)

                # Do not retry on auth errors
                if status_code in (401, 403):
                    raise

                # Retry on rate-limit / transient errors
                if status_code in (429, 502, 503, 504):
                    if attempt < self.max_retries - 1:
                        sleep_time = self.backoff * (2 ** attempt)
                        time.sleep(sleep_time)
                        continue

                # For other errors, retry once more as a safety net
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff)
                    continue

                raise

        raise last_error  # type: ignore[misc]

    @staticmethod
    def _extract_status_code(exc: Exception) -> Optional[int]:
        """Try to extract HTTP status code from an OpenAI exception."""
        # OpenAI errors expose status_code on the exception directly or via response
        if hasattr(exc, "status_code"):
            return getattr(exc, "status_code")
        response = getattr(exc, "response", None)
        if response is not None and hasattr(response, "status_code"):
            return getattr(response, "status_code")
        return None
