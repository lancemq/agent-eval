"""Tests for the multi-judge panel."""

from agent_eval.judges.base import BaseJudge
from agent_eval.judges.panel import MultiJudgePanel, JudgePanelResult


class ConstantJudge(BaseJudge):
    name = "constant_high"

    def score(self, task, output):
        return 0.9

    def explain(self, task, output, score):
        return "Always high"


class ConstantLowJudge(BaseJudge):
    name = "constant_low"

    def score(self, task, output):
        return 0.1

    def explain(self, task, output, score):
        return "Always low"


class VariableJudge(BaseJudge):
    name = "variable"

    def __init__(self, fixed_score: float = 0.5):
        self.fixed_score = fixed_score

    def score(self, task, output):
        return self.fixed_score

    def explain(self, task, output, score):
        return f"Variable: {score}"


def test_panel_single_judge():
    panel = MultiJudgePanel([ConstantJudge()])
    result = panel.evaluate({}, {})
    assert result["_final"] == 0.9
    assert "constant_high" in result
    assert result["constant_high"]["score"] == 0.9
    assert result["_consistency"] == 1.0


def test_panel_weighted_aggregation():
    judges = [ConstantJudge(), ConstantLowJudge()]
    weights = {"constant_high": 0.8, "constant_low": 0.2}
    panel = MultiJudgePanel(judges, aggregation="weighted", weights=weights)
    result = panel.evaluate({}, {})
    expected = 0.9 * 0.8 + 0.1 * 0.2
    assert abs(result["_final"] - expected) < 0.01


def test_panel_median_aggregation():
    judges = [VariableJudge(0.9), VariableJudge(0.5), VariableJudge(0.1)]
    panel = MultiJudgePanel(judges, aggregation="median")
    result = panel.evaluate({}, {})
    assert result["_final"] == 0.5


def test_panel_mean_aggregation():
    judges = [VariableJudge(0.8), VariableJudge(0.6), VariableJudge(0.4)]
    panel = MultiJudgePanel(judges, aggregation="mean")
    result = panel.evaluate({}, {})
    assert abs(result["_final"] - 0.6) < 0.01


def test_panel_unanimous_aggregation():
    judges = [ConstantJudge(), ConstantJudge()]
    panel = MultiJudgePanel(judges, aggregation="unanimous")
    result = panel.evaluate({}, {})
    assert result["_final"] == 1.0

    judges2 = [ConstantJudge(), ConstantLowJudge()]
    panel2 = MultiJudgePanel(judges2, aggregation="unanimous")
    result2 = panel2.evaluate({}, {})
    assert result2["_final"] == 0.0


def test_panel_majority_aggregation():
    judges = [ConstantJudge(), ConstantJudge(), ConstantLowJudge()]
    panel = MultiJudgePanel(judges, aggregation="majority")
    result = panel.evaluate({}, {})
    assert result["_final"] == 1.0


def test_panel_consistency():
    judges = [ConstantJudge(), ConstantJudge()]
    panel = MultiJudgePanel(judges)
    result = panel.evaluate({}, {})
    assert result["_consistency"] == 1.0

    judges2 = [ConstantJudge(), ConstantLowJudge()]
    panel2 = MultiJudgePanel(judges2)
    result2 = panel2.evaluate({}, {})
    assert result2["_consistency"] < 0.5


def test_judge_panel_result_wrapper():
    panel = MultiJudgePanel([ConstantJudge()])
    result = panel.evaluate({}, {})
    wrapper = JudgePanelResult(result)
    assert wrapper.final_score == 0.9
    assert wrapper.consistency == 1.0
    assert "constant_high" in wrapper.judge_scores
    assert wrapper.passed is True


def test_panel_with_error_judge():
    class ErrorJudge(BaseJudge):
        name = "error_judge"

        def score(self, task, output):
            raise ValueError("Judge error")

        def explain(self, task, output, score):
            return "error"

    panel = MultiJudgePanel([ConstantJudge(), ErrorJudge()])
    result = panel.evaluate({}, {})
    assert "error_judge" in result
    assert result["error_judge"]["score"] is None
    assert "error" in result["error_judge"]
    assert result["_judge_errors"] == 1
    # Valid judge still contributes to the final score
    assert result["_final"] == 0.9


def test_get_judge_details():
    judges = [ConstantJudge(), ConstantLowJudge()]
    panel = MultiJudgePanel(judges)
    details = panel.get_judge_details()
    assert len(details) == 2
    assert details[0]["name"] == "constant_high"