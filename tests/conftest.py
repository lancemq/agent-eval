"""Shared fixtures and configuration for tests."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"
    agent.generate.return_value = "test response"
    agent.chat.return_value = "test chat response"
    agent.act.return_value = {"type": "finish"}
    return agent