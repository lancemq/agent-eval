"""Tests for AgentUnderTest and JSON extraction."""

from agent_eval.orchestrator.agent import AgentUnderTest, OpenAIAgent


def test_extract_json_fenced_block():
    response = 'Some text\n```json\n{"type": "tool_call", "tool": "calc"}\n```\nmore text'
    result = AgentUnderTest._extract_json(response)
    assert result == {"type": "tool_call", "tool": "calc"}


def test_extract_json_plain_dict():
    response = 'Here is the action: {"type": "finish"} thanks!'
    result = AgentUnderTest._extract_json(response)
    assert result == {"type": "finish"}


def test_extract_json_nested_dict():
    response = 'Result: {"type": "tool_call", "params": {"x": 1}} end.'
    result = AgentUnderTest._extract_json(response)
    assert result == {"type": "tool_call", "params": {"x": 1}}


def test_extract_json_no_dict():
    response = "No JSON here at all"
    result = AgentUnderTest._extract_json(response)
    assert result["type"] == "error"
    assert "JSON parse failed" in result["reason"]


def test_extract_json_invalid_json():
    response = "Broken: {type: finish}"
    result = AgentUnderTest._extract_json(response)
    assert result["type"] == "error"


def test_openai_agent_init_uses_llm_client():
    agent = OpenAIAgent(model="gpt-4o", timeout=45.0, max_retries=5)
    assert agent.client.model == "gpt-4o"
    assert agent.client.timeout == 45.0
    assert agent.client.max_retries == 5
