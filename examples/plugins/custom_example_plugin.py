"""Example custom plugin."""

from typing import Any, Dict, List
from agent_eval.plugins.base import BasePlugin, EvaluationType, EvalContext, EvalResult, register_plugin


@register_plugin
class CustomExamplePlugin(BasePlugin):
    name = "custom_example"
    version = "1.0"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["instruction_following", "creativity"]
    description = "Example custom plugin"

    def __init__(self):
        super().__init__()
        self.test_cases = []

    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.test_cases = config.get("test_cases", [
            {
                "id": "test_1",
                "instruction": "Write a haiku about AI.",
                "expected_topics": ["ai", "artificial", "intelligence", "machine"],
                "min_length": 10,
            },
            {
                "id": "test_2",
                "instruction": "Explain what a callback function is in 2-3 sentences.",
                "expected_topics": ["function", "callback", "passed", "called"],
                "min_length": 20,
            },
            {
                "id": "test_3",
                "instruction": "List exactly 3 benefits of using Python for data science.",
                "expected_topics": [],
                "min_length": 20,
            },
        ])

    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        return self.test_cases

    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        response = context.agent_under_test.generate(task["instruction"])
        return {"response": response, "instruction": task["instruction"]}

    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        response = output["response"]
        score = 0.0
        details = {}

        expected_topics = task.get("expected_topics", [])
        if expected_topics:
            response_lower = response.lower()
            matched = sum(1 for t in expected_topics if t.lower() in response_lower)
            topic_score = matched / len(expected_topics)
            score += topic_score * 0.5
            details["topic_match"] = f"{matched}/{len(expected_topics)}"

        min_length = task.get("min_length", 0)
        if len(response) >= min_length:
            score += 0.3
            details["length_check"] = "passed"
        else:
            details["length_check"] = f"too_short: {len(response)} < {min_length}"

        passed = score >= 0.5

        return EvalResult(
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=min(score + 0.2, 1.0),
            raw_score={"raw_score": score},
            details=details,
            artifacts=[response],
            passed=passed,
            execution_time_ms=0,
            task_id=task["id"]
        )