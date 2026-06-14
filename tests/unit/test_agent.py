"""Tests for AgentUnderTest adapters and JSON extraction."""

import sys
import types

import pytest

from agent_eval.orchestrator.agent import AgentUnderTest, CallableAgent, OpenAIAgent


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


def test_callable_agent_preserves_native_act_method():
    class ToolAgent:
        name = "tool_agent"
        version = "2.1"

        def generate(self, prompt):
            return "unused"

        def act(self, state, available_tools, goal):
            return {
                "type": "tool_call",
                "tool": available_tools[0],
                "params": {"goal": goal, "seen": state["seen"]},
            }

    agent = CallableAgent.from_object(ToolAgent())

    assert agent.name == "tool_agent"
    assert agent.version == "2.1"
    assert agent.act({"seen": True}, ["calculator"], "solve") == {
        "type": "tool_call",
        "tool": "calculator",
        "params": {"goal": "solve", "seen": True},
    }


def test_callable_agent_supports_configured_method_aliases_and_response_objects():
    class Response:
        content = "hello from object"

    class ThirdPartyAgent:
        def invoke(self, prompt):
            return Response()

        def send_messages(self, messages):
            return {"text": messages[-1]["content"]}

        def decide_action(self, state, available_tools, goal):
            return '{"type": "finish", "reason": "done"}'

    agent = CallableAgent.from_object(
        ThirdPartyAgent(),
        config={
            "methods": {
                "generate": "invoke",
                "chat": "send_messages",
                "act": "decide_action",
            },
            "name": "third_party",
        },
    )

    assert agent.name == "third_party"
    assert agent.generate("hi") == "hello from object"
    assert agent.chat([{"role": "user", "content": "chat text"}]) == "chat text"
    assert agent.act({}, [], "finish") == {"type": "finish", "reason": "done"}


def test_callable_agent_from_module_supports_factory_function():
    module = types.ModuleType("fake_agent_module")

    class FactoryAgent:
        def __init__(self, model):
            self.model = model

        def invoke(self, prompt):
            return {"output": f"{self.model}: {prompt}"}

    def build_agent(model):
        return FactoryAgent(model)

    module.build_agent = build_agent
    sys.modules[module.__name__] = module
    try:
        agent = CallableAgent.from_module(
            "fake_agent_module:build_agent",
            {"init": {"model": "demo"}, "methods": {"generate": "invoke"}},
        )
    finally:
        sys.modules.pop(module.__name__, None)

    assert agent.generate("ping") == "demo: ping"


def test_callable_agent_reports_missing_generate_capability():
    with pytest.raises(TypeError, match="generate"):
        CallableAgent.from_object(object())
