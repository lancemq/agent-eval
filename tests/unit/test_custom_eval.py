import csv
import json

import pytest

from agent_eval.evaluators.custom_eval_plugin import CustomEvalEvaluator, validate_custom_eval_config


def custom_eval_config(tasks=None, scorer=None):
    return {
        "evaluations": [
            {
                "id": "qa",
                "name": "QA",
                "dimensions": ["correctness"],
                "task_source": {
                    "type": "inline",
                    "items": tasks or [{"task_id": "q1", "input": "Capital?", "expected": "Paris"}],
                },
                "prompt": {"mode": "generate", "template": "Question: {input}"},
                "scoring": {
                    "threshold": 0.7,
                    "aggregation": "weighted",
                    "scorers": [scorer or {"id": "exact", "type": "exact_match", "weight": 1, "dimension": "correctness", "params": {"case_sensitive": False}}],
                },
            }
        ]
    }


def test_custom_eval_exact_match_passes(mock_agent):
    mock_agent.generate.return_value = "paris"
    evaluator = CustomEvalEvaluator()
    evaluator.setup(custom_eval_config())
    task = evaluator.generate_tasks(None)[0]

    output = evaluator.execute_task(task, _context(mock_agent))
    result = evaluator.evaluate(task, output, _context(mock_agent))

    assert result.score == 1.0
    assert result.passed is True
    assert result.dimension_scores == {"correctness": 1.0}
    assert result.details["rendered_prompt"] == "Question: Capital?"


def test_custom_eval_exact_match_fails(mock_agent):
    mock_agent.generate.return_value = "London"
    evaluator = CustomEvalEvaluator()
    evaluator.setup(custom_eval_config())
    task = evaluator.generate_tasks(None)[0]

    output = evaluator.execute_task(task, _context(mock_agent))
    result = evaluator.evaluate(task, output, _context(mock_agent))

    assert result.score == 0.0
    assert result.passed is False


def test_custom_eval_weighted_aggregation(mock_agent):
    mock_agent.generate.return_value = "Paris"
    config = custom_eval_config(scorer={"id": "exact", "type": "exact_match", "weight": 3, "dimension": "correctness", "params": {"case_sensitive": False}})
    config["evaluations"][0]["scoring"]["scorers"].append({"id": "length", "type": "length", "weight": 1, "dimension": "format", "params": {"max_words": 0}})
    config["evaluations"][0]["scoring"]["scorers"][1]["params"] = {"max_chars": 1}
    evaluator = CustomEvalEvaluator()
    evaluator.setup(config)
    task = evaluator.generate_tasks(None)[0]

    output = evaluator.execute_task(task, _context(mock_agent))
    result = evaluator.evaluate(task, output, _context(mock_agent))

    assert result.score == 0.75
    assert result.dimension_scores["correctness"] == 1.0
    assert result.dimension_scores["format"] == 0.0


def test_custom_eval_chat_mode(mock_agent):
    mock_agent.chat.return_value = "Paris"
    config = custom_eval_config()
    config["evaluations"][0]["prompt"] = {
        "mode": "chat",
        "messages": [{"role": "user", "content": "Question: {input}"}],
    }
    evaluator = CustomEvalEvaluator()
    evaluator.setup(config)
    task = evaluator.generate_tasks(None)[0]

    output = evaluator.execute_task(task, _context(mock_agent))

    mock_agent.chat.assert_called_once_with([{"role": "user", "content": "Question: Capital?"}])
    assert output["response"] == "Paris"


def test_custom_eval_json_file_source(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([{"task_id": "q1", "input": "A", "expected": "B"}]))
    config = custom_eval_config()
    config["evaluations"][0]["task_source"] = {"type": "file", "path": str(path), "format": "json"}
    evaluator = CustomEvalEvaluator()
    evaluator.setup(config)

    tasks = evaluator.generate_tasks(None)

    assert tasks[0]["input"] == "A"


def test_custom_eval_csv_file_source(tmp_path):
    path = tmp_path / "tasks.csv"
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["task_id", "input", "expected"])
        writer.writeheader()
        writer.writerow({"task_id": "q1", "input": "A", "expected": "B"})
    config = custom_eval_config()
    config["evaluations"][0]["task_source"] = {"type": "file", "path": str(path), "format": "csv"}
    evaluator = CustomEvalEvaluator()
    evaluator.setup(config)

    tasks = evaluator.generate_tasks(None)

    assert tasks[0]["expected"] == "B"


def test_custom_eval_validate_unknown_scorer():
    config = custom_eval_config(scorer={"id": "bad", "type": "missing_scorer"})

    errors = validate_custom_eval_config(config)

    assert errors
    assert errors[0]["field"].endswith(".type")


def test_custom_eval_template_missing_field_raises(mock_agent):
    config = custom_eval_config()
    config["evaluations"][0]["prompt"]["template"] = "Question: {missing}"
    evaluator = CustomEvalEvaluator()
    evaluator.setup(config)
    task = evaluator.generate_tasks(None)[0]

    with pytest.raises(KeyError):
        evaluator.execute_task(task, _context(mock_agent))


def _context(agent):
    class Context:
        agent_under_test = agent

    return Context()
