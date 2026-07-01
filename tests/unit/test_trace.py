"""Tests for the trace system: schema, store, collector, normalizers, task generator, analyzer, replay."""

import json
import os
import tempfile
import pytest

from agent_eval.trace.schema import TraceRecord, TraceStep, ToolCallSummary
from agent_eval.trace.store import TraceStore
from agent_eval.trace.collector import TraceCollector
from agent_eval.trace.normalizers import (
    CustomJSONNormalizer, SelfEvalNormalizer,
    OpenTelemetryNormalizer, LangSmithNormalizer,
    get_normalizer, auto_detect_normalizer, list_normalizers,
)
from agent_eval.trace.task_generator import TaskGenerator
from agent_eval.datasets import DatasetBuilder
from agent_eval.trace.analyzer import TraceAnalyzer
from agent_eval.trace.replay import TracePlayer


# =========================== Schema Tests ===========================

class TestTraceSchema:
    def test_trace_record_defaults(self):
        r = TraceRecord()
        assert r.trace_id  # auto-generated UUID
        assert r.trace_type == "single_turn"
        assert r.success is True

    def test_to_dict_roundtrip(self):
        r = TraceRecord(
            input="hello",
            output="hi",
            messages=[{"role": "user", "content": "hello"}],
            trace_type="single_turn",
        )
        d = r.to_dict()
        r2 = TraceRecord.from_dict(d)
        assert r2.input == "hello"
        assert r2.output == "hi"
        assert r2.trace_type == "single_turn"

    def test_trace_step(self):
        s = TraceStep(step_index=0, action_type="tool_call", action={"tool": "search"})
        d = s.to_dict()
        s2 = TraceStep.from_dict(d)
        assert s2.action_type == "tool_call"
        assert s2.action["tool"] == "search"

    def test_tool_call_summary(self):
        tc = ToolCallSummary(name="search", arguments={"q": "test"}, result="found")
        d = tc.to_dict()
        tc2 = ToolCallSummary.from_dict(d)
        assert tc2.name == "search"

    def test_infer_type(self):
        assert TraceRecord(input="hi", output="hello").infer_type() == "single_turn"
        assert TraceRecord(messages=[{"r": "u", "c": "1"}, {"r": "a", "c": "2"}, {"r": "u", "c": "3"}, {"r": "a", "c": "4"}]).infer_type() == "multi_turn"
        assert TraceRecord(trajectory=[TraceStep(0, action_type="tool_call", action={"tool": "x"})]).infer_type() == "tool_use"

    def test_computed_properties(self):
        r = TraceRecord(
            messages=[{"r": "u", "c": "1"}, {"r": "a", "c": "2"}],
            tool_calls=[ToolCallSummary(name="a")],
            trajectory=[TraceStep(0)],
        )
        assert r.num_turns == 1
        assert r.num_tool_calls == 1
        assert r.num_steps == 1


# =========================== Store Tests ===========================

class TestTraceStore:
    def test_json_backend(self):
        with tempfile.TemporaryDirectory() as d:
            store = TraceStore(backend="json", path=d)
            r = TraceRecord(trace_id="t1", input="hello", output="hi")
            store.save(r)
            loaded = store.load("t1")
            assert loaded is not None
            assert loaded.input == "hello"

    def test_memory_backend(self):
        store = TraceStore(backend="memory")
        r = TraceRecord(trace_id="t1", input="test")
        store.save(r)
        assert store.count() == 1
        assert store.load("t1").input == "test"

    def test_query_by_type(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1", trace_type="single_turn"))
        store.save(TraceRecord(trace_id="t2", trace_type="tool_use"))
        results = store.query({"trace_type": "tool_use"})
        assert len(results) == 1
        assert results[0].trace_id == "t2"

    def test_query_by_success(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1", success=True))
        store.save(TraceRecord(trace_id="t2", success=False))
        assert len(store.query({"success": True})) == 1
        assert len(store.query({"success": False})) == 1

    def test_query_by_quality(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1", quality_score=0.9))
        store.save(TraceRecord(trace_id="t2", quality_score=0.3))
        results = store.query({"min_quality": 0.5})
        assert len(results) == 1
        assert results[0].trace_id == "t1"

    def test_delete(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1"))
        assert store.delete("t1") is True
        assert store.count() == 0

    def test_stats(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1", trace_type="single_turn", agent_name="a1", success=True, duration_ms=100))
        store.save(TraceRecord(trace_id="t2", trace_type="tool_use", agent_name="a1", success=False, duration_ms=200))
        stats = store.stats()
        assert stats["total"] == 2
        assert stats["by_type"]["single_turn"] == 1
        assert stats["success_rate"] == 0.5

    def test_import_dir(self):
        with tempfile.TemporaryDirectory() as d:
            raw = {"trace_id": "imp1", "input": "imported", "output": "result"}
            with open(os.path.join(d, "trace.json"), "w") as f:
                json.dump(raw, f)
            store = TraceStore(backend="json", path=d + "_store")
            count = store.import_dir(d, source="custom")
            assert count == 1
            assert store.count() == 1


# =========================== Collector Tests ===========================

class TestTraceCollector:
    def test_context_manager(self):
        store = TraceStore(backend="memory")
        collector = TraceCollector(store=store)
        with collector.trace(agent_name="test_agent") as tb:
            tb.set_input("hello")
            tb.set_output("hi")
        assert store.count() == 1
        r = store.query({})[0]
        assert r.input == "hello"
        assert r.output == "hi"

    def test_context_manager_with_tools(self):
        store = TraceStore(backend="memory")
        collector = TraceCollector(store=store)
        with collector.trace(agent_name="test", trace_type="tool_use") as tb:
            tb.set_input("What's the weather?")
            tb.add_tool_call("weather_api", {"city": "SF"}, "72F sunny")
            tb.set_output("It's 72F and sunny in SF.")
        r = store.query({})[0]
        assert r.num_tool_calls == 1
        assert r.tool_calls[0].name == "weather_api"
        assert r.num_steps == 1  # one trajectory step

    def test_exception_capture(self):
        store = TraceStore(backend="memory")
        collector = TraceCollector(store=store)
        with pytest.raises(ValueError):
            with collector.trace(agent_name="test") as tb:
                tb.set_input("hello")
                raise ValueError("crash")
        r = store.query({})[0]
        assert r.success is False
        assert "crash" in r.error

    def test_submit_raw(self):
        store = TraceStore(backend="memory")
        collector = TraceCollector(store=store)
        collector.submit_raw({"input": "hello", "output": "hi"}, source="custom")
        assert store.count() == 1


# =========================== Normalizer Tests ===========================

class TestNormalizers:
    def test_custom_json(self):
        n = CustomJSONNormalizer(field_map={"input": "query", "output": "response"})
        record = n.normalize({"query": "hello", "response": "hi"})
        assert record.input == "hello"
        assert record.output == "hi"

    def test_custom_json_with_trajectory(self):
        n = CustomJSONNormalizer()
        record = n.normalize({
            "input": "search for cats",
            "output": "found 3 cats",
            "tool_calls": [{"name": "search", "arguments": {"q": "cats"}, "result": "3 results"}],
        })
        assert record.num_tool_calls == 1
        assert record.tool_calls[0].name == "search"
        assert record.trace_type == "tool_use"

    def test_self_eval_normalizer(self):
        n = SelfEvalNormalizer()
        record = n.normalize({
            "task_id": "task_001",
            "evaluator_name": "mmlu",
            "evaluation_type": "benchmark",
            "score": 0.85,
            "passed": True,
            "details": {
                "output": "The answer is C",
                "task": {"prompt": "What is the capital of France?"},
            },
        })
        assert record.input == "What is the capital of France?"
        assert record.output == "The answer is C"
        assert record.success is True
        assert record.source == "self_eval"

    def test_otel_normalizer(self):
        n = OpenTelemetryNormalizer()
        record = n.normalize({
            "spans": [
                {
                    "trace_id": "trace1",
                    "span_id": "span1",
                    "name": "llm.chat",
                    "attributes": {"llm.system": "openai", "llm.prompts": "hello"},
                    "start_time": 1000,
                    "end_time": 1500,
                },
                {
                    "trace_id": "trace1",
                    "span_id": "span2",
                    "parent_span_id": "span1",
                    "name": "tool.search",
                    "attributes": {"tool.name": "search", "tool.arguments": {"q": "test"}},
                    "start_time": 1100,
                    "end_time": 1200,
                },
            ]
        })
        assert record.trace_id == "trace1"
        assert record.num_tool_calls == 1
        assert record.tool_calls[0].name == "search"

    def test_langsmith_normalizer(self):
        n = LangSmithNormalizer()
        record = n.normalize({
            "id": "run1",
            "session_name": "my_agent",
            "inputs": {"input": "hello"},
            "outputs": {"output": "hi"},
            "child_runs": [
                {"run_type": "tool", "name": "search", "inputs": {"q": "test"}, "outputs": {"output": "results"}},
            ],
            "status": "S",
        })
        assert record.input == "hello"
        assert record.output == "hi"
        assert record.num_tool_calls == 1

    def test_auto_detect(self):
        n1 = auto_detect_normalizer({"spans": [{"span_id": "s1"}]})
        assert isinstance(n1, OpenTelemetryNormalizer)

        n2 = auto_detect_normalizer({"child_runs": []})
        assert isinstance(n2, LangSmithNormalizer)

        n3 = auto_detect_normalizer({"evaluator_name": "mmlu", "evaluation_type": "benchmark"})
        assert isinstance(n3, SelfEvalNormalizer)

    def test_get_normalizer(self):
        assert isinstance(get_normalizer("custom"), CustomJSONNormalizer)
        assert isinstance(get_normalizer("self_eval"), SelfEvalNormalizer)

    def test_list_normalizers(self):
        names = list_normalizers()
        assert "custom" in names
        assert "self_eval" in names
        assert "opentelemetry" in names
        assert "langsmith" in names


# =========================== Task Generator Tests ===========================

class TestTaskGenerator:
    def test_single_turn(self):
        gen = TaskGenerator()
        trace = TraceRecord(input="What is 2+2?", output="4", trace_type="single_turn")
        task = gen.generate(trace)
        assert task.task_type == "single_turn"
        assert task.input == "What is 2+2?"
        assert task.expected_output == "4"
        assert "answer_correctness" in task.scorers

    def test_tool_use(self):
        gen = TaskGenerator()
        trace = TraceRecord(
            input="Search for cats",
            output="Found 3 cats",
            trace_type="tool_use",
            tool_calls=[ToolCallSummary(name="search", arguments={"q": "cats"})],
            trajectory=[TraceStep(0, "tool_call", {"tool": "search", "params": {"q": "cats"}})],
        )
        task = gen.generate(trace)
        assert task.task_type == "tool_use"
        assert "search" in task.available_tools
        assert "tool_call_correctness" in task.scorers

    def test_multi_turn(self):
        gen = TaskGenerator()
        trace = TraceRecord(
            input="hello",
            output="hi there",
            trace_type="multi_turn",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
                {"role": "user", "content": "how are you?"},
                {"role": "assistant", "content": "good"},
            ],
        )
        task = gen.generate(trace)
        assert task.task_type == "multi_turn"
        assert "conversation_quality" in task.scorers

    def test_batch(self):
        gen = TaskGenerator()
        traces = [
            TraceRecord(input="q1", output="a1", trace_type="single_turn"),
            TraceRecord(input="q2", output="a2", trace_type="single_turn"),
        ]
        tasks = gen.generate_batch(traces)
        assert len(tasks) == 2


# =========================== Dataset Builder Tests ===========================

class TestDatasetBuilder:
    def test_from_traces(self):
        builder = DatasetBuilder(name="test_ds")
        traces = [
            TraceRecord(trace_id="t1", input="q1", output="a1", quality_score=0.9),
            TraceRecord(trace_id="t2", input="q2", output="a2", quality_score=0.3),
        ]
        builder.from_traces(traces, min_quality=0.5)
        assert len(builder.tasks) == 1

    def test_deduplicate(self):
        builder = DatasetBuilder(name="test_ds")
        traces = [
            TraceRecord(trace_id="t1", input="same", output="a1", quality_score=0.8),
            TraceRecord(trace_id="t2", input="same", output="a2", quality_score=0.6),
        ]
        builder.from_traces(traces, deduplicate=True)
        assert len(builder.tasks) == 1

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ds.json")
            builder = DatasetBuilder(name="test_ds")
            builder.from_traces([TraceRecord(trace_id="t1", input="q", output="a")])
            builder.save(path)
            loaded = DatasetBuilder.load(path)
            assert loaded.name == "test_ds"
            assert len(loaded.tasks) == 1


# =========================== Analyzer Tests ===========================

class TestAnalyzer:
    def test_analyze(self):
        analyzer = TraceAnalyzer()
        traces = [
            TraceRecord(trace_id="t1", trace_type="single_turn", agent_name="a1", success=True, duration_ms=100, input="What is Python?", output="A programming language"),
            TraceRecord(trace_id="t2", trace_type="tool_use", agent_name="a1", success=False, duration_ms=200, input="Search for cats", output="", error="timeout"),
            TraceRecord(trace_id="t3", trace_type="multi_turn", agent_name="a2", success=True, duration_ms=300, input="Write a function to sort", output="def sort(arr)..."),
        ]
        report = analyzer.analyze(traces)
        assert report.total == 3
        assert report.type_distribution["single_turn"] == 1
        assert report.type_distribution["tool_use"] == 1
        assert report.success_rate == pytest.approx(2/3)

    def test_quality_scoring(self):
        analyzer = TraceAnalyzer()
        traces = [
            TraceRecord(input="full input", output="full output", success=True, messages=[{"r": "u", "c": "1"}, {"r": "a", "c": "2"}], trajectory=[TraceStep(0)], tool_calls=[ToolCallSummary(name="t")]),
            TraceRecord(input="", output="", success=False),
        ]
        scores = analyzer.score_quality(traces)
        assert scores[0].overall > scores[1].overall
        assert scores[0].completeness > scores[1].completeness

    def test_golden_set_diverse(self):
        analyzer = TraceAnalyzer()
        traces = [
            TraceRecord(trace_id=f"t{i}", input=f"question {i} about topic {i%5}", output=f"answer {i}", success=True, trace_type="single_turn")
            for i in range(100)
        ]
        golden = analyzer.select_golden_set(traces, n=10, strategy="diverse")
        assert len(golden) <= 10
        assert len(golden) > 0

    def test_golden_set_failure(self):
        analyzer = TraceAnalyzer()
        traces = [
            TraceRecord(trace_id="t1", success=False, error="err1"),
            TraceRecord(trace_id="t2", success=True),
            TraceRecord(trace_id="t3", success=False, error="err2"),
        ]
        golden = analyzer.select_golden_set(traces, n=10, strategy="failure")
        assert all(not t.success for t in golden)

    def test_intent_clusters(self):
        analyzer = TraceAnalyzer()
        traces = [
            TraceRecord(input="Write a Python function to sort", output="..."),
            TraceRecord(input="What is the meaning of life?", output="42"),
            TraceRecord(input="Search the web for cats", output="results"),
        ]
        report = analyzer.analyze(traces)
        assert len(report.intent_clusters) > 0


# =========================== Replay Tests ===========================

class TestTracePlayer:
    def test_replay_single_turn(self):
        traces = {
            "t1": TraceRecord(trace_id="t1", input="hello", output="hi"),
        }
        player = TracePlayer(traces)
        assert player.generate("hello", task_id="t1") == "hi"

    def test_replay_not_found(self):
        player = TracePlayer({})
        assert player.generate("unknown") == "[REPLAY_TRACE_NOT_FOUND]"

    def test_replay_tool_call(self):
        trace = TraceRecord(
            trace_id="t1",
            input="search for cats",
            output="found cats",
            trajectory=[
                TraceStep(0, "tool_call", {"type": "tool_call", "tool": "search", "params": {"q": "cats"}}),
                TraceStep(1, "finish", {"type": "finish", "result": "found cats"}),
            ],
        )
        player = TracePlayer({"t1": trace})
        action1 = player.act({"task_id": "t1"}, ["search"], "search for cats")
        assert action1.get("tool") == "search" or action1.get("type") == "tool_call"
        player.act({"task_id": "t1"}, ["search"], "search for cats")
        player.reset("t1")

    def test_from_store(self):
        store = TraceStore(backend="memory")
        store.save(TraceRecord(trace_id="t1", input="hello", output="hi"))
        player = TracePlayer.from_store(store)
        assert player.generate("hello", task_id="t1") == "hi"

    def test_chat_replay(self):
        trace = TraceRecord(
            trace_id="t1",
            input="hello",
            output="hi there",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )
        player = TracePlayer({"t1": trace})
        result = player.chat([{"role": "user", "content": "hello"}], task_id="t1")
        assert result == "hi there"
