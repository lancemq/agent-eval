"""MMLU Benchmark Plugin."""

from typing import Any, Dict, List
from agent_eval.plugins.base import BasePlugin, EvaluationType, EvalContext, EvalResult, register_plugin


@register_plugin
class MMLUPlugin(BasePlugin):
    name = "mmlu"
    version = "1.0"
    evaluation_type = EvaluationType.BENCHMARK
    supported_dimensions = ["knowledge", "reasoning"]
    description = "Massive Multitask Language Understanding benchmark"
    
    def __init__(self):
        super().__init__()
        self.dataset = None
        self.split = "test"
        self.judge = None
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.split = config.get("split", "test")
        self.subset = config.get("subset", "all")
        self.judge_config = config.get("judge", {"type": "exact_match"})
        self._load_dataset()
        self._init_judge()
    
    def _load_dataset(self) -> None:
        try:
            from datasets import load_dataset
            if self.subset == "all":
                self.dataset = load_dataset("cais/mmlu", "all")
            else:
                self.dataset = load_dataset("cais/mmlu", self.subset)
        except ImportError:
            raise RuntimeError("datasets library required: pip install datasets")
        except Exception as e:
            raise RuntimeError(f"Failed to load MMLU dataset: {e}")
    
    def _init_judge(self) -> None:
        from agent_eval.judges.factory import JudgeFactory
        self.judge = JudgeFactory.create(self.judge_config)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        tasks = []
        data = self.dataset[self.split]
        for idx, row in enumerate(data):
            tasks.append({
                "task_id": f"mmlu_{self.subset}_{idx}",
                "question": row["question"],
                "choices": row["choices"],
                "answer": row["answer"],
                "subject": row.get("subject", "unknown"),
            })
        return tasks
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        prompt = self._format_prompt(task)
        response = context.agent_under_test.generate(prompt)
        return {"response": response, "prompt": prompt}
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        predicted = self._extract_answer(output["response"])
        expected = task["answer"]
        
        result = self.judge.judge(
            predicted=predicted,
            expected=expected,
            task=task,
            output=output
        )
        
        return EvalResult(
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=result.score,
            raw_score=result.raw_score,
            details=result.details,
            artifacts=[output["response"]],
            passed=result.passed,
            execution_time_ms=result.execution_time_ms,
            task_id=task["task_id"]
        )
    
    def _format_prompt(self, task: Dict[str, Any]) -> str:
        choices_str = "\n".join([f"{chr(65+i)}. {choice}" for i, choice in enumerate(task["choices"])])
        return f"""Question: {task['question']}

Choices:
{choices_str}

Answer:"""
    
    def _extract_answer(self, response: str) -> str:
        response = response.strip().upper()
        for char in ["A", "B", "C", "D"]:
            if response.startswith(char) or f" {char}" in response or f"({char})" in response:
                return char
        return response[0] if response else ""