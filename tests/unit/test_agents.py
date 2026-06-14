"""Tests for the universal agent integration layer."""

import pytest
from unittest.mock import MagicMock, patch

from agent_eval.agents import (
    AgentFactory,
    AgentAdapter,
    FunctionAgent,
    HTTPAgentAdapter,
    LangChainAdapter,
    AutoGenAdapter,
    CrewAIAdapter,
    LangGraphAdapter,
    agent_type,
    detect_capabilities,
    coerce_response,
    extract_json,
    AgentCapability,
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
from agent_eval.orchestrator.agent import AgentUnderTest


# =========================== Protocol Tests ===========================

class TestAgentProtocol:
    def test_detect_capabilities_generate(self):
        class SimpleAgent:
            def generate(self, prompt):
                return "hi"
        caps = detect_capabilities(SimpleAgent())
        assert AgentCapability.GENERATE in caps

    def test_detect_capabilities_multiple(self):
        class FullAgent:
            def generate(self, prompt): ...
            def chat(self, messages): ...
            def act(self, state, tools, goal): ...
        caps = detect_capabilities(FullAgent())
        cap_names = {c.value for c in caps}
        assert "generate" in cap_names
        assert "chat" in cap_names
        assert "act" in cap_names

    def test_detect_capabilities_callable(self):
        caps = detect_capabilities(lambda x: x)
        assert AgentCapability.GENERATE in caps

    def test_coerce_response_string(self):
        r = coerce_response("hello")
        assert r.content == "hello"

    def test_coerce_response_dict_content(self):
        r = coerce_response({"content": "test"})
        assert r.content == "test"

    def test_coerce_response_dict_output(self):
        r = coerce_response({"output": "result"})
        assert r.content == "result"

    def test_coerce_response_openai_object(self):
        mock_msg = MagicMock()
        mock_msg.content = "OpenAI response"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        r = coerce_response(mock_resp)
        assert r.content == "OpenAI response"

    def test_coerce_response_langchain_style(self):
        class LCMock:
            content = "LangChain response"
            tool_calls = []
            choices = None  # prevent OpenAI path
        r = coerce_response(LCMock())
        assert r.content == "LangChain response"

    def test_extract_json_fenced(self):
        text = "Here is the result:\n```json\n{\"type\": \"finish\"}\n```"
        result = extract_json(text)
        assert result["type"] == "finish"

    def test_extract_json_inline(self):
        text = 'Action: {"type": "tool_call", "tool": "search"}'
        result = extract_json(text)
        assert result["type"] == "tool_call"

    def test_extract_json_error(self):
        result = extract_json("no json here")
        assert result["type"] == "error"


# =========================== Provider Tests ===========================

class TestProviders:
    def test_list_providers(self):
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "ollama" in providers
        assert "http" in providers

    def test_auto_detect_openai(self):
        assert auto_detect_provider("gpt-4o") == "openai"
        assert auto_detect_provider("o1-preview") == "openai"

    def test_auto_detect_anthropic(self):
        assert auto_detect_provider("claude-sonnet-4-20250514") == "anthropic"

    def test_auto_detect_ollama(self):
        assert auto_detect_provider("llama3") == "ollama"
        assert auto_detect_provider("mistral") == "ollama"

    def test_get_provider_openai(self):
        provider = get_provider("openai", api_key="test-key")
        assert isinstance(provider, OpenAIProvider)
        assert provider.api_key == "test-key"

    def test_get_provider_ollama(self):
        provider = get_provider("ollama", base_url="http://localhost:11434")
        assert isinstance(provider, OllamaProvider)

    def test_get_provider_claude_alias(self):
        provider = get_provider("claude")
        assert isinstance(provider, AnthropicProvider)

    def test_get_provider_http(self):
        provider = get_provider("http", base_url="http://localhost:8000")
        assert isinstance(provider, HTTPProvider)

    def test_get_provider_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_register_custom_provider(self):
        class CustomProvider(BaseLLMProvider):
            provider_name = "custom"
            def chat(self, messages, model="", **kwargs):
                return "custom response"
        register_provider("my_custom", CustomProvider)
        provider = get_provider("my_custom")
        assert isinstance(provider, CustomProvider)


class TestOpenAIProvider:
    def test_init_with_env_var(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider()
            assert provider.api_key == "env-key"

    def test_init_with_explicit_key(self):
        provider = OpenAIProvider(api_key="explicit-key")
        assert provider.api_key == "explicit-key"

    @patch("builtins.__import__")
    def test_missing_openai_lib(self, mock_import):
        mock_import.side_effect = ImportError("not found")
        provider = OpenAIProvider(api_key="test")
        with pytest.raises(RuntimeError, match="openai library required"):
            provider._get_client()


# =========================== Adapter Tests ===========================

class TestFunctionAgent:
    def test_generate_simple(self):
        def my_fn(prompt):
            return f"Response to: {prompt}"
        agent = FunctionAgent(my_fn, name="test_agent")
        assert agent.generate("hello") == "Response to: hello"
        assert agent.name == "test_agent"

    def test_generate_with_dict_return(self):
        def my_fn(prompt):
            return {"content": "dict response"}
        agent = FunctionAgent(my_fn)
        assert agent.generate("test") == "dict response"

    def test_chat_with_chat_fn(self):
        def gen(prompt): return "gen"
        def chat_fn(messages): return messages[-1]["content"]
        agent = FunctionAgent(gen, chat_fn=chat_fn)
        result = agent.chat([{"role": "user", "content": "hi"}])
        assert result == "hi"

    def test_chat_fallback_to_generate(self):
        def gen(prompt): return f"echo: {prompt}"
        agent = FunctionAgent(gen)
        result = agent.chat([{"role": "user", "content": "hi"}])
        assert "hi" in result

    def test_act_fallback_prompt(self):
        def gen(prompt): return '{"type": "finish", "result": "done"}'
        agent = FunctionAgent(gen)
        result = agent.act({}, [], "test goal")
        assert result["type"] == "finish"

    def test_wrap_object(self):
        class MyAgent:
            name = "wrapped"
            def generate(self, prompt):
                return f"wrapped: {prompt}"
        agent = FunctionAgent.wrap_object(MyAgent())
        assert agent.name == "wrapped"
        assert agent.generate("test") == "wrapped: test"

    def test_wrap_object_no_generate_raises(self):
        class NoMethods:
            pass
        with pytest.raises(TypeError, match="no generate method"):
            FunctionAgent.wrap_object(NoMethods())

    def test_from_callable(self):
        def my_fn(prompt): return "callable result"
        agent = FunctionAgent.from_callable(my_fn, name="from_callable")
        assert agent.generate("x") == "callable result"
        assert agent.name == "from_callable"

    def test_async_function(self):
        import asyncio
        async def async_gen(prompt):
            await asyncio.sleep(0)
            return "async result"
        agent = FunctionAgent(async_gen)
        assert agent.generate("test") == "async result"


class TestAgentAdapter:
    def test_adapter_wraps_agent(self):
        class MyAgent:
            def generate(self, prompt): return f"resp: {prompt}"
            def chat(self, messages): return "chat resp"
        adapter = AgentAdapter(MyAgent(), name="test")
        assert adapter.generate("hi") == "resp: hi"
        assert adapter.chat([{"role": "user", "content": "hi"}]) == "chat resp"

    def test_adapter_capabilities(self):
        class FullAgent:
            def generate(self, p): ...
            def chat(self, m): ...
            def act(self, s, t, g): ...
        adapter = AgentAdapter(FullAgent())
        caps = adapter.capabilities
        assert "generate" in caps
        assert "chat" in caps
        assert "act" in caps

    def test_adapter_method_map_override(self):
        class MyAgent:
            def custom_generate(self, prompt): return "custom"
        adapter = AgentAdapter(MyAgent(), methods={"generate": "custom_generate"})
        assert adapter.generate("hi") == "custom"

    def test_adapter_no_method_raises(self):
        class Empty:
            pass
        adapter = AgentAdapter(Empty())
        with pytest.raises(TypeError, match="No suitable method"):
            adapter.generate("test")


class TestLangChainAdapter:
    def test_generate_with_invoke(self):
        class LCAgent:
            def invoke(self, prompt, **kwargs):
                return f"LC: {prompt}"
        adapter = LangChainAdapter(LCAgent())
        assert adapter.generate("hello") == "LC: hello"

    def test_generate_with_run(self):
        class LCAgent:
            def run(self, prompt):
                return f"run: {prompt}"
        adapter = LangChainAdapter(LCAgent())
        assert adapter.generate("hello") == "run: hello"

    def test_generate_with_predict(self):
        class LCAgent:
            def predict(self, prompt):
                return f"predict: {prompt}"
        adapter = LangChainAdapter(LCAgent())
        assert adapter.generate("hello") == "predict: hello"


class TestAutoGenAdapter:
    def test_generate_with_generate_reply(self):
        class AGAgent:
            def generate_reply(self, messages=None, sender=None):
                return f"AG: {messages[0]['content']}"
        adapter = AutoGenAdapter(AGAgent())
        assert adapter.generate("test") == "AG: test"

    def test_chat_with_generate_reply(self):
        class AGAgent:
            def generate_reply(self, messages=None, sender=None):
                return messages[-1]["content"]
        adapter = AutoGenAdapter(AGAgent())
        result = adapter.chat([{"role": "user", "content": "hi"}])
        assert result == "hi"


class TestCrewAIAdapter:
    def test_generate_with_execute_task(self):
        class CAAgent:
            def execute_task(self, task, context=""):
                return f"CA: {task}"
        adapter = CrewAIAdapter(CAAgent())
        assert adapter.generate("do something") == "CA: do something"

    def test_chat_flatten_messages(self):
        class CAAgent:
            def execute_task(self, task, context=""):
                return f"CA: {task}"
        adapter = CrewAIAdapter(CAAgent())
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        result = adapter.chat(messages)
        assert "hello" in result and "hi" in result


class TestLangGraphAdapter:
    def test_generate_with_invoke(self):
        class LGAgent:
            def invoke(self, input_data, **kwargs):
                msgs = input_data.get("messages", [])
                return {"messages": [{"role": "assistant", "content": f"LG: {msgs[0]['content']}"}]}
        adapter = LangGraphAdapter(LGAgent(), input_key="messages")
        assert adapter.generate("test") == "LG: test"

    def test_chat_with_invoke(self):
        class LGAgent:
            def invoke(self, input_data, **kwargs):
                msgs = input_data.get("messages", [])
                last = msgs[-1]
                return {"messages": [{"role": "assistant", "content": f"reply to {last['content']}"}]}
        adapter = LangGraphAdapter(LGAgent())
        result = adapter.chat([{"role": "user", "content": "hello"}])
        assert "hello" in result


class TestHTTPAgentAdapter:
    def test_init_defaults(self):
        agent = HTTPAgentAdapter(base_url="http://localhost:8000", model="test-model")
        assert agent.base_url == "http://localhost:8000"
        assert agent.model == "test-model"
        assert agent.name == "http_agent"

    @patch("urllib.request.urlopen")
    def test_generate_makes_request(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "API response"}}]}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        agent = HTTPAgentAdapter(base_url="http://localhost:8000", model="test")
        result = agent.generate("hello")
        assert result == "API response"

    @patch("urllib.request.urlopen")
    def test_chat_makes_request(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "chat response"}}]}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        agent = HTTPAgentAdapter(base_url="http://localhost:8000")
        result = agent.chat([{"role": "user", "content": "hi"}])
        assert result == "chat response"


# =========================== Factory Tests ===========================

class TestAgentFactory:
    def test_create_from_existing_aut(self):
        original = FunctionAgent(lambda p: "existing")
        result = AgentFactory.create(original)
        assert result is original

    def test_create_from_object(self):
        class MyAgent:
            def generate(self, prompt): return "obj response"
        agent = AgentFactory.create(MyAgent())
        assert agent.generate("test") == "obj response"

    def test_create_openai_spec(self):
        agent = AgentFactory.create("openai:gpt-4o-mini")
        assert isinstance(agent, AgentUnderTest)
        assert agent.name == "openai_agent"

    def test_create_http_url_spec(self):
        agent = AgentFactory.create("http://localhost:8000")
        assert isinstance(agent, HTTPAgentAdapter)
        assert agent.base_url == "http://localhost:8000"

    def test_create_http_prefix_spec(self):
        agent = AgentFactory.create("http://localhost:9000")
        assert isinstance(agent, HTTPAgentAdapter)

    def test_create_dict_function_spec(self):
        def my_fn(prompt): return "fn response"
        agent = AgentFactory.create({"type": "function", "callable": my_fn})
        assert isinstance(agent, FunctionAgent)
        assert agent.generate("test") == "fn response"

    def test_create_dict_http_spec(self):
        agent = AgentFactory.create({"type": "http", "base_url": "http://localhost:8000"})
        assert isinstance(agent, HTTPAgentAdapter)

    def test_create_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            AgentFactory.create("nonsense_spec")

    def test_create_dict_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing 'type'"):
            AgentFactory.create({"model": "gpt-4"})

    def test_create_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown agent type"):
            AgentFactory.create({"type": "nonexistent_framework"})

    def test_list_types(self):
        types = AgentFactory.list_types()
        assert "openai" in types
        assert "anthropic" in types
        assert "http" in types
        assert "function" in types
        assert "langchain" in types
        assert len(types) == len(set(types))  # no duplicates

    def test_register_custom_adapter(self):
        @agent_type("my_custom_type")
        class CustomAdapter(FunctionAgent):
            pass
        types = AgentFactory.list_types()
        assert "my_custom_type" in types


class TestAgentFactoryProviderSpecs:
    def test_anthropic_spec(self):
        agent = AgentFactory.create("anthropic:claude-sonnet-4-20250514")
        assert isinstance(agent, AgentUnderTest)

    def test_ollama_spec(self):
        agent = AgentFactory.create("ollama:llama3")
        assert isinstance(agent, AgentUnderTest)

    def test_claude_alias_spec(self):
        agent = AgentFactory.create("claude:claude-sonnet-4-20250514")
        assert isinstance(agent, AgentUnderTest)


class TestAgentFactoryModuleImport:
    def test_create_from_module_no_colon_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            AgentFactory.create("just_a_module_name")

    def test_create_from_module_missing_colon_raises(self):
        with pytest.raises((ValueError, ModuleNotFoundError)):
            AgentFactory.create("nonexistent_module:SomeClass")
