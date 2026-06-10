"""Tests for the unified LLM client."""

from unittest.mock import MagicMock, patch
import pytest
from agent_eval.llm_client import LLMClient


def test_llm_client_chat_success():
    client = LLMClient(model="gpt-4o-mini", timeout=30.0, max_retries=1)
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=" Hello "))]

    with patch.object(client, "_get_client") as mock_get:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        mock_get.return_value = mock_openai

        resp = client.chat(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
        )
        assert resp == mock_response
        mock_openai.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
            timeout=30.0,
        )


def test_llm_client_retries_on_429():
    client = LLMClient(model="gpt-4o-mini", timeout=10.0, max_retries=3, backoff=0.01)

    class Fake429(Exception):
        status_code = 429

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]

    with patch.object(client, "_get_client") as mock_get:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = [
            Fake429("rate limited"),
            Fake429("rate limited"),
            mock_response,
        ]
        mock_get.return_value = mock_openai

        resp = client.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp == mock_response
        assert mock_openai.chat.completions.create.call_count == 3


def test_llm_client_no_retry_on_401():
    client = LLMClient(model="gpt-4o-mini", timeout=10.0, max_retries=3)

    class Fake401(Exception):
        status_code = 401

    with patch.object(client, "_get_client") as mock_get:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = Fake401("unauthorized")
        mock_get.return_value = mock_openai

        with pytest.raises(Fake401):
            client.chat(messages=[{"role": "user", "content": "hi"}])
        assert mock_openai.chat.completions.create.call_count == 1


def test_extract_status_code():
    class WithStatus(Exception):
        status_code = 503

    class WithResponse(Exception):
        response = MagicMock(status_code=502)

    assert LLMClient._extract_status_code(WithStatus()) == 503
    assert LLMClient._extract_status_code(WithResponse()) == 502
    assert LLMClient._extract_status_code(RuntimeError("plain")) is None
