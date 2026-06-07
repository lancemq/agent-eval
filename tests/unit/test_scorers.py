"""Tests for all scorer implementations."""

import pytest
from agent_eval.scorers.base import BaseScorer, ScorerResult
from agent_eval.scorers.factory import ScorerFactory
from agent_eval.scorers.deterministic import (
    ExactMatchScorer, NumericMatchScorer, RegexScorer, JSONScorer,
    KeywordScorer, LengthScorer, ContainsAnyScorer, ContainsAllScorer,
)
from agent_eval.scorers.agent import TaskEfficiencyScorer, ToolCallCorrectnessScorer
from agent_eval.scorers.ensemble import EnsembleScorer, ThresholdScorer


class TestScorerResult:
    def test_default_values(self):
        r = ScorerResult(name="test", score=0.5)
        assert r.name == "test"
        assert r.score == 0.5
        assert r.passed is True
        assert r.reason == ""
        assert r.metadata == {}
        assert r.execution_time_ms == 0

    def test_to_dict(self):
        r = ScorerResult(name="test", score=0.8, reason="good", passed=True, metadata={"k": "v"}, execution_time_ms=100)
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["score"] == 0.8
        assert d["reason"] == "good"
        assert d["metadata"] == {"k": "v"}


class TestScorerFactory:
    def test_create_by_name(self):
        s = ScorerFactory.create("exact_match")
        assert isinstance(s, ExactMatchScorer)

    def test_create_by_dict(self):
        s = ScorerFactory.create({"type": "exact_match", "case_sensitive": False})
        assert isinstance(s, ExactMatchScorer)

    def test_create_returns_scorer_instance(self):
        inner = ExactMatchScorer()
        s = ScorerFactory.create(inner)
        assert s is inner

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown scorer"):
            ScorerFactory.create("nonexistent_scorer_xyz")

    def test_list_scorers(self):
        scorers = ScorerFactory.list_scorers()
        assert len(scorers) >= 20
        assert "exact_match" in scorers
        assert "g_eval" in scorers
        assert "faithfulness" in scorers
        assert "ensemble" in scorers

    def test_create_with_params(self):
        s = ScorerFactory.create({"type": "keyword", "required_keywords": ["hello", "world"]})
        assert isinstance(s, KeywordScorer)
        assert s.required == ["hello", "world"]

    def test_create_numeric_match(self):
        s = ScorerFactory.create({"type": "numeric_match", "tolerance": 0.01})
        assert isinstance(s, NumericMatchScorer)


class TestExactMatchScorer:
    def test_match(self):
        s = ExactMatchScorer()
        r = s.score("hello", expected="hello")
        assert r.score == 1.0
        assert r.passed is True

    def test_no_match(self):
        s = ExactMatchScorer()
        r = s.score("hello", expected="world")
        assert r.score == 0.0
        assert r.passed is False

    def test_case_insensitive(self):
        s = ExactMatchScorer(case_sensitive=False)
        r = s.score("Hello", expected="hello")
        assert r.score == 1.0

    def test_strip(self):
        s = ExactMatchScorer(strip=True)
        r = s.score("  hello  ", expected="hello")
        assert r.score == 1.0

    def test_no_expected(self):
        s = ExactMatchScorer()
        r = s.score("hello")
        assert r.score == 0.0
        assert r.passed is False


class TestNumericMatchScorer:
    def test_exact_match(self):
        s = NumericMatchScorer()
        r = s.score("42", expected="42")
        assert r.score == 1.0

    def test_within_tolerance(self):
        s = NumericMatchScorer(tolerance=0.1)
        r = s.score("3.14159", expected="3.141")
        assert r.score == 1.0

    def test_outside_tolerance(self):
        s = NumericMatchScorer(tolerance=0.1)
        r = s.score("10", expected="5")
        assert r.score < 1.0

    def test_no_number_in_output(self):
        s = NumericMatchScorer()
        r = s.score("no numbers here")
        assert r.score == 0.0
        assert r.passed is False


class TestRegexScorer:
    def test_match(self):
        s = RegexScorer(pattern=r"\d{3}-\d{4}")
        r = s.score("Call 555-1234")
        assert r.score == 1.0

    def test_no_match(self):
        s = RegexScorer(pattern=r"\d{3}-\d{4}")
        r = s.score("No phone here")
        assert r.score == 0.0

    def test_optional_match(self):
        s = RegexScorer(pattern=r"\d+", required=False)
        r = s.score("no digits")
        assert r.score == 1.0

    def test_invalid_regex(self):
        s = RegexScorer()
        r = s.score("test", pattern=r"[invalid")
        assert r.score == 0.0
        assert r.passed is False


class TestJSONScorer:
    def test_valid_json(self):
        s = JSONScorer()
        r = s.score('{"name": "test", "value": 42}')
        assert r.score == 1.0
        assert r.passed is True

    def test_invalid_json(self):
        s = JSONScorer()
        r = s.score("not json")
        assert r.score == 0.0
        assert r.passed is False

    def test_missing_keys(self):
        s = JSONScorer(required_keys=["name", "email"])
        r = s.score('{"name": "test"}')
        assert r.score < 1.0
        assert r.passed is False

    def test_json_in_code_block(self):
        s = JSONScorer(required_keys=["name"])
        r = s.score('```json\n{"name": "test"}\n```')
        assert r.score == 1.0


class TestKeywordScorer:
    def test_all_present(self):
        s = KeywordScorer(required_keywords=["hello", "world"])
        r = s.score("hello world")
        assert r.score == 1.0
        assert r.passed is True

    def test_some_missing(self):
        s = KeywordScorer(required_keywords=["hello", "world", "foo"])
        r = s.score("hello world")
        assert r.score == 2 / 3
        assert r.passed is True

    def test_forbidden_present(self):
        s = KeywordScorer(forbidden_keywords=["bad", "evil"])
        r = s.score("this is bad")
        assert r.score == 0.0
        assert r.passed is False

    def test_required_and_forbidden(self):
        s = KeywordScorer(required_keywords=["good"], forbidden_keywords=["bad"])
        r = s.score("good things")
        assert r.score == 1.0
        r2 = s.score("good and bad")
        assert r2.score == 0.0


class TestLengthScorer:
    def test_min_chars(self):
        s = LengthScorer(min_chars=10)
        r = s.score("short")
        assert r.score == 0.0
        assert r.passed is False

    def test_max_chars(self):
        s = LengthScorer(max_chars=10)
        r = s.score("this is too long for the limit")
        assert r.score == 0.0
        assert r.passed is False

    def test_within_bounds(self):
        s = LengthScorer(min_chars=2, max_chars=100, min_words=1)
        r = s.score("hello world")
        assert r.score == 1.0
        assert r.passed is True

    def test_min_words(self):
        s = LengthScorer(min_words=3)
        r = s.score("one two")
        assert r.score == 0.0

    def test_no_constraints(self):
        s = LengthScorer()
        r = s.score("anything goes")
        assert r.score == 1.0


class TestContainsAnyScorer:
    def test_found(self):
        s = ContainsAnyScorer(options=["hello", "world", "test"])
        r = s.score("hello there")
        assert r.score == 1.0
        assert r.passed is True

    def test_not_found(self):
        s = ContainsAnyScorer(options=["hello", "world"])
        r = s.score("nothing matches")
        assert r.score == 0.0
        assert r.passed is False

    def test_case_insensitive(self):
        s = ContainsAnyScorer(options=["Hello"], case_sensitive=False)
        r = s.score("hello")
        assert r.score == 1.0


class TestContainsAllScorer:
    def test_all_found(self):
        s = ContainsAllScorer(required=["hello", "world"])
        r = s.score("hello beautiful world")
        assert r.score == 1.0
        assert r.passed is True

    def test_some_missing(self):
        s = ContainsAllScorer(required=["hello", "world", "missing"])
        r = s.score("hello world")
        assert r.score == 2 / 3
        assert r.passed is False

    def test_no_requirements(self):
        s = ContainsAllScorer(required=[])
        r = s.score("anything")
        assert r.score == 1.0


class TestTaskEfficiencyScorer:
    def test_optimal_steps(self):
        trajectory = [{"action": {"type": "tool_call"}}]
        s = TaskEfficiencyScorer(optimal_steps=1)
        r = s.score("", trajectory=trajectory)
        assert r.score == 1.0

    def test_many_steps(self):
        trajectory = [{"action": {"type": "tool_call"}} for _ in range(20)]
        s = TaskEfficiencyScorer(optimal_steps=1, max_steps=10)
        r = s.score("", trajectory=trajectory)
        assert r.score == 0.0

    def test_partial_efficiency(self):
        trajectory = [{"action": {"type": "tool_call"}} for _ in range(5)]
        s = TaskEfficiencyScorer(optimal_steps=1, max_steps=10)
        r = s.score("", trajectory=trajectory)
        assert 0.0 < r.score < 1.0


class TestToolCallCorrectnessScorer:
    def test_all_correct(self):
        trajectory = [
            {"action": {"type": "tool_call", "tool": "calculator", "params": {"expr": "1+1"}}},
            {"action": {"type": "finish"}},
        ]
        s = ToolCallCorrectnessScorer()
        r = s.score("", trajectory=trajectory, available_tools=["calculator", "search"])
        assert r.score >= 0.5

    def test_missing_required_tool(self):
        trajectory = [
            {"action": {"type": "tool_call", "tool": "search", "params": {}}},
            {"action": {"type": "finish"}},
        ]
        s = ToolCallCorrectnessScorer()
        r = s.score("", trajectory=trajectory, available_tools=["search", "calculator"],
                     must_call=["calculator"])
        assert r.score < 1.0
        assert "calculator" in str(r.reason)

    def test_no_tool_calls(self):
        trajectory = [{"action": {"type": "finish"}}]
        s = ToolCallCorrectnessScorer()
        r = s.score("", trajectory=trajectory, available_tools=["calculator"])
        assert r.score == 0.0


class TestEnsembleScorer:
    def test_simple_ensemble(self):
        s = EnsembleScorer(
            scorers=[ExactMatchScorer(), KeywordScorer(required_keywords=["hello"])],
        )
        r = s.score("hello", expected="hello")
        assert 0.0 <= r.score <= 1.0
        assert "individual_scores" in r.metadata

    def test_weighted_ensemble(self):
        s = EnsembleScorer(
            scorers=[ExactMatchScorer(), ExactMatchScorer()],
            weights=[0.8, 0.2],
            aggregation="weighted",
        )
        r = s.score("test", expected="test")
        assert r.score == 1.0

    def test_median_aggregation(self):
        exact = ExactMatchScorer()
        class HalfScorer(BaseScorer):
            name = "half"
            def score(self, output, **kwargs):
                return ScorerResult(name="half", score=0.5, reason="")
        s = EnsembleScorer(
            scorers=[exact, HalfScorer(), HalfScorer()],
            aggregation="median",
        )
        r = s.score("hello", expected="world")  # exact=0, half=0.5, half=0.5 -> median=0.5
        assert r.score == 0.5

    def test_min_aggregation(self):
        s = EnsembleScorer(
            scorers=[ExactMatchScorer(), ExactMatchScorer()],
            aggregation="min",
        )
        r1 = s.score("a", expected="a")
        assert r1.score == 1.0
        r2 = s.score("a", expected="b")
        assert r2.score == 0.0

    def test_majority_aggregation(self):
        class PassScorer(BaseScorer):
            name = "pass"
            def score(self, output, **kwargs):
                return ScorerResult(name="pass", score=1.0, reason="")
        class FailScorer(BaseScorer):
            name = "fail"
            def score(self, output, **kwargs):
                return ScorerResult(name="fail", score=0.0, reason="")
        s = EnsembleScorer(
            scorers=[PassScorer(), PassScorer(), FailScorer()],
            aggregation="majority",
        )
        r = s.score("test")
        assert r.score == 1.0


class TestThresholdScorer:
    def test_passes_threshold(self):
        inner = ExactMatchScorer()
        s = ThresholdScorer(scorer=inner, threshold=0.8)
        r = s.score("test", expected="test")
        assert r.passed is True

    def test_fails_threshold(self):
        inner = ExactMatchScorer()
        s = ThresholdScorer(scorer=inner, threshold=0.8)
        r = s.score("test", expected="different")
        assert r.passed is False

    def test_creation_from_dict(self):
        s = ThresholdScorer(scorer={"type": "exact_match"}, threshold=0.9)
        assert isinstance(s.inner, ExactMatchScorer)


class TestScorerRegistry:
    def test_all_registered_scorers_create(self):
        """Verify all registered scorer types can be instantiated."""
        scorers = ScorerFactory.list_scorers()
        for name in scorers:
            try:
                s = ScorerFactory.create(name)
                assert isinstance(s, BaseScorer), f"{name} is not a BaseScorer"
            except TypeError:
                # Some scorers need constructor params (like RegexScorer needs pattern)
                if name == "regex_match":
                    s = ScorerFactory.create({"type": "regex_match", "pattern": r"test"})
                    assert isinstance(s, RegexScorer)
                elif name == "keyword":
                    s = ScorerFactory.create({"type": "keyword", "required_keywords": ["test"]})
                    assert isinstance(s, KeywordScorer)
                elif name == "length":
                    s = ScorerFactory.create({"type": "length", "min_chars": 1})
                    assert isinstance(s, LengthScorer)
                elif name == "contains_any":
                    s = ScorerFactory.create({"type": "contains_any", "options": ["a"]})
                    assert isinstance(s, ContainsAnyScorer)
                elif name == "contains_all":
                    s = ScorerFactory.create({"type": "contains_all", "required": ["a"]})
                    assert isinstance(s, ContainsAllScorer)
                elif name == "threshold":
                    s = ScorerFactory.create({"type": "threshold", "scorer": {"type": "exact_match"}})
                    assert isinstance(s, ThresholdScorer)
                elif name == "ensemble":
                    s = ScorerFactory.create({"type": "ensemble", "scorers": [{"type": "exact_match"}]})
                    assert isinstance(s, EnsembleScorer)
                else:
                    raise


class TestCustomScorerDecorator:
    def test_scorer_decorator_registers_class(self):
        from agent_eval.scorers import scorer, BaseScorer, ScorerResult

        @scorer("test_custom_decorator")
        class TestCustomScorer(BaseScorer):
            name = "test_custom_decorator"
            def score(self, output: str, **kwargs) -> ScorerResult:
                return ScorerResult(name=self.name, score=0.5, reason="decorator test", passed=True)

        s = ScorerFactory.create("test_custom_decorator")
        assert isinstance(s, TestCustomScorer)
        result = s.score("anything")
        assert result.score == 0.5

    def test_scorer_decorator_works_with_judge_factory(self):
        from agent_eval.judges.factory import JudgeFactory
        from agent_eval.scorers import scorer, BaseScorer, ScorerResult

        @scorer("bridge_test_scorer")
        class BridgeTestScorer(BaseScorer):
            name = "bridge_test_scorer"
            def score(self, output: str, **kwargs) -> ScorerResult:
                return ScorerResult(name=self.name, score=0.9, reason="bridge", passed=True)

        judge = JudgeFactory.create({"type": "bridge_test_scorer"})
        from agent_eval.judges.factory import ScorerBridge
        assert isinstance(judge, ScorerBridge)
        result = judge.judge(output="test")
        assert result.score == 0.9