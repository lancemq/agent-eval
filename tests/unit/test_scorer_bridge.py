"""Tests for ScorerBridge integration with JudgeFactory."""

from agent_eval.judges.base import BaseJudge, JudgeResult
from agent_eval.judges.factory import JudgeFactory, ScorerBridge
from agent_eval.scorers.deterministic import ExactMatchScorer, JSONScorer


class TestScorerBridge:
    def test_bridge_wraps_scorer(self):
        scorer = ExactMatchScorer()
        bridge = ScorerBridge(scorer)
        assert isinstance(bridge, BaseJudge)
        assert bridge.name == "exact_match"

    def test_bridge_scores_via_judge_interface(self):
        scorer = ExactMatchScorer()
        bridge = ScorerBridge(scorer)
        score = bridge.score({"expected": "hello"}, "hello")
        assert score == 1.0

    def test_bridge_judge_method(self):
        scorer = JSONScorer(required_keys=["name"])
        bridge = ScorerBridge(scorer)
        result = bridge.judge(output='{"name": "test"}')
        assert isinstance(result, JudgeResult)
        assert result.score == 1.0
        assert result.passed is True

    def test_bridge_explain(self):
        scorer = ExactMatchScorer()
        bridge = ScorerBridge(scorer)
        explanation = bridge.explain({}, "test", 0.5)
        assert isinstance(explanation, str)


class TestJudgeFactoryScorerIntegration:
    def test_factory_creates_scorer_via_bridge_for_unknown_types(self):
        # "answer_correctness" is NOT in the judge registry, so falls through to ScorerFactory
        judge = JudgeFactory.create({"type": "answer_correctness"})
        assert isinstance(judge, ScorerBridge)

    def test_factory_creates_json_scorer(self):
        # "json_valid" is NOT in the judge registry -> uses ScorerFactory bridge
        judge = JudgeFactory.create({"type": "json_valid", "required_keys": ["name", "age"]})
        assert isinstance(judge, ScorerBridge)
        result = judge.judge(output='{"name": "Alice", "age": 30}')
        assert result.passed is True

        result2 = judge.judge(output='{"name": "Alice"}')
        assert result2.passed is False

    def test_factory_creates_keyword_scorer(self):
        judge = JudgeFactory.create({"type": "keyword", "required_keywords": ["api", "endpoint"]})
        result = judge.judge(output="The REST API endpoint is /users")
        assert result.score > 0

    def test_factory_creates_contains_any(self):
        judge = JudgeFactory.create({"type": "contains_any", "options": ["error", "fail", "exception"]})
        result = judge.judge(output="This is fine")
        assert result.score == 0.0

    def test_factory_fallback_to_scorer_on_unknown(self):
        judge = JudgeFactory.create({"type": "answer_correctness"})
        assert isinstance(judge, ScorerBridge)

    def test_exact_match_uses_builtin_judge_not_scorer_bridge(self):
        # "exact_match" exists in judge registry, so it's NOT a ScorerBridge
        judge = JudgeFactory.create({"type": "exact_match"})
        # The built-in ExactMatchJudge is used instead
        result = judge.judge(
            expected="hello",
            predicted="hello",
            task={"expected": "hello", "predicted": "hello"},
            output="hello"
        )
        assert result.score == 1.0

    def test_scorer_bridge_in_panel(self):
        from agent_eval.judges.panel import MultiJudgePanel

        # Use scorer types NOT in the judge registry
        j1 = JudgeFactory.create({"type": "contains_any", "options": ["hello", "world"]})
        j2 = JudgeFactory.create({"type": "keyword", "required_keywords": ["hello"], "forbidden_keywords": ["bad"]})

        panel = MultiJudgePanel([j1, j2])
        result = panel.evaluate({"expected": "hello world"}, "hello world")
        assert result["_final"] > 0
        assert "contains_any" in result or "keyword" in result

    def test_bridge_with_panel_score_method(self):
        from agent_eval.judges.panel import MultiJudgePanel

        j1 = JudgeFactory.create({"type": "contains_any", "options": ["hello"]})
        panel = MultiJudgePanel([j1])
        result = panel.evaluate({}, "hello world")
        assert result["_final"] >= 0.5