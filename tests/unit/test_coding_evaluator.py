"""Tests for coding evaluator execution behavior."""

from unittest.mock import MagicMock

from agent_eval.evaluators.base import EvalContext
from agent_eval.evaluators.dynamic.coding_plugin import CodingEvaluator


def test_coding_plugin_uses_task_entry_point_for_tests():
    agent = MagicMock()
    agent.generate.return_value = """
```python
def add_one(x):
    return x + 1
```
"""
    evaluator = CodingEvaluator()
    evaluator.setup({"judges": []})

    task = {
        "task_id": "entry_point",
        "prompt": "write add_one",
        "entry_point": "add_one",
        "test_cases": [{"input": (1,), "expected": 2}],
    }
    output = evaluator.execute_task(task, EvalContext(agent_under_test=agent, task_config={}))

    assert output["entry_point"] == "add_one"
    assert output["test_results"][0]["passed"] is True
