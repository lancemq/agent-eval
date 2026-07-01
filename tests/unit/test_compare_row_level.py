"""Tests for row-level report comparison."""

import pytest

from agent_eval.orchestrator.result_store import ResultStore
from agent_eval.orchestrator import EvaluationReport


def _make_report(run_id, task_results, overall=0.5, agent_name="agent_a"):
    return EvaluationReport(
        run_id=run_id,
        timestamp="2026-01-01T00:00:00Z",
        agent_name=agent_name,
        agent_version="1.0",
        summary={"overall_score": overall, "dimensions": {"acc": overall}},
        evaluator_results={},
        metadata={"agent_name": agent_name},
        task_results=task_results,
    )


def test_compare_row_level_aligned(tmp_path):
    store = ResultStore({"type": "json", "output_dir": str(tmp_path)})
    r1 = _make_report("r1", {"custom_eval": [
        {"task_id": "t1", "score": 0.4, "passed": False, "response": "A"},
        {"task_id": "t2", "score": 0.9, "passed": True, "response": "B"},
    ]})
    r2 = _make_report("r2", {"custom_eval": [
        {"task_id": "t1", "score": 0.8, "passed": True, "response": "A2"},
        {"task_id": "t2", "score": 0.9, "passed": True, "response": "B"},
    ]})
    store.save(r1)
    store.save(r2)

    result = store.compare_row_level(["r1", "r2"])
    assert result["labels"] == ["r1", "r2"]
    assert result["summary"]["aligned"] == 2
    aligned = result["aligned_rows"]
    t1 = next(r for r in aligned if r["task_id"] == "t1")
    assert t1["score_deltas"]["r2"] == pytest.approx(0.4)
    assert t1["responses"]["r2"] == "A2"


def test_compare_row_level_added_removed(tmp_path):
    store = ResultStore({"type": "json", "output_dir": str(tmp_path)})
    r1 = _make_report("r1", {"p": [
        {"task_id": "t1", "score": 0.5, "passed": True, "response": "x"},
        {"task_id": "t2", "score": 0.5, "passed": True, "response": "y"},
    ]})
    r2 = _make_report("r2", {"p": [
        {"task_id": "t2", "score": 0.5, "passed": True, "response": "y"},
        {"task_id": "t3", "score": 0.5, "passed": True, "response": "z"},
    ]})
    store.save(r1)
    store.save(r2)

    result = store.compare_row_level(["r1", "r2"])
    assert result["summary"]["added"] == 1
    assert result["summary"]["removed"] == 1
    assert result["summary"]["aligned"] == 1
    assert result["added"][0]["task_id"] == "t3"
    assert result["removed"][0]["task_id"] == "t1"
