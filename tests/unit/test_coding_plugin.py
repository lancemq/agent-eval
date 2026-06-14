"""Tests for coding plugin execution behavior."""

from unittest.mock import MagicMock

from agent_eval.plugins.base import EvalContext
from agent_eval.plugins.dynamic.coding_plugin import CodingPlugin


def test_coding_plugin_uses_task_entry_point_for_tests():
    agent = MagicMock()
    agent.generate.return_value = """
```python
def add_one(x):
    return x + 1
```
"""
    plugin = CodingPlugin()
    plugin.setup({"judges": []})

    task = {
        "task_id": "entry_point",
        "prompt": "write add_one",
        "entry_point": "add_one",
        "test_cases": [{"input": (1,), "expected": 2}],
    }
    output = plugin.execute_task(task, EvalContext(agent_under_test=agent, task_config={}))

    assert output["entry_point"] == "add_one"
    assert output["test_results"][0]["passed"] is True
