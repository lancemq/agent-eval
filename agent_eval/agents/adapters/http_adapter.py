"""HTTP/REST agent adapter for any OpenAI-compatible API endpoint."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from agent_eval.orchestrator.agent import AgentUnderTest
from agent_eval.agents.protocol import extract_json


class HTTPAgentAdapter(AgentUnderTest):
    """Adapter for any HTTP-based agent API.

    Supports:
      - OpenAI-compatible /v1/chat/completions endpoints
      - Custom REST API endpoints with configurable request/response mapping
      - vLLM, TGI, LocalAI, FastChat, etc.

    Configuration:
      base_url: API base URL (e.g., http://localhost:8000)
      endpoint: API path (default: /v1/chat/completions)
      api_key: Bearer token (default: from OPENAI_API_KEY env)
      model: Model name to send in request
      system_prompt: System message prepended to all requests
      temperature, max_tokens: Generation params
      headers: Extra HTTP headers
    """

    def __init__(
        self,
        base_url: str,
        model: str = "default",
        endpoint: str = "/v1/chat/completions",
        api_key: Optional[str] = None,
        system_prompt: str = "You are a helpful AI assistant.",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        timeout: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
        name: str = "http_agent",
        version: str = "1.0",
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.extra_headers = headers or {}
        self.name = name
        self.version = version

    def _send_request(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        body: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)

        url = f"{self.base_url}{self.endpoint}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # OpenAI-compatible response
            if "choices" in result:
                return result["choices"][0]["message"]["content"].strip()
            # Generic response
            return str(result.get("content") or result.get("output") or result)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self._send_request(messages, **kwargs)

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        formatted = [{"role": "system", "content": self.system_prompt}]
        formatted.extend({"role": m["role"], "content": m["content"]} for m in messages)
        return self._send_request(formatted, **kwargs)

    def act(
        self,
        state: Dict[str, Any],
        available_tools: List[str],
        goal: str,
    ) -> Dict[str, Any]:
        prompt = (
            f"Goal: {goal}\nCurrent State: {json.dumps(state)}\n"
            f"Available Tools: {available_tools}\n\n"
            f"Decide on the next action. Return JSON: "
            f'{{"type": "tool_call", "tool": "...", "params": {{...}}}}'
            f' or {{"type": "finish", "result": "..."}}'
        )
        response = self.generate(prompt)
        return extract_json(response)
