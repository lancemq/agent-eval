"""GSM8K Benchmark Plugin for mathematical reasoning."""

import re
from typing import Any, Dict, List
from agent_eval.plugins.base import BasePlugin, EvaluationType, EvalContext, EvalResult, register_plugin


@register_plugin
class GSM8KPlugin(BasePlugin):
    name = "gsm8k"
    version = "1.0"
    evaluation_type = EvaluationType.BENCHMARK
    supported_dimensions = ["mathematical_reasoning", "multi_step_reasoning"]
    description = "Grade School Math 8K benchmark"
    
    def __init__(self):
        super().__init__()
        self.dataset = None
        self.split = "test"
        self.judge = None
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.split = config.get("split", "test")
        self.judge_config = config.get("judge", {"type": "numeric_answer"})
        self._load_dataset()
        self._init_judge()
    
    def _load_dataset(self) -> None:
        try:
            from datasets import load_dataset
            self.dataset = load_dataset("gsm8k", "main")[self.split]
        except ImportError:
            raise RuntimeError("datasets library required: pip install datasets")
        except Exception as e:
            raise RuntimeError(f"Failed to load GSM8K dataset: {e}")
    
    def _init_judge(self) -> None:
        from agent_eval.judges.factory import JudgeFactory
        self.judge = JudgeFactory.create(self.judge_config)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        tasks = []
        for idx, row in enumerate(self.dataset):
            tasks.append({
                "task_id": f"gsm8k_{idx}",
                "question": row["question"],
                "answer": row["answer"],
            })
        return tasks
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        prompt = self._format_prompt(task)
        response = context.agent_under_test.generate(prompt)
        return {"response": response, "prompt": prompt}
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        predicted = self._extract_answer(output["response"])
        expected = self._extract_answer(task["answer"])
        
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
        return f"""Solve this math problem step by step.

Question: {task['question']}

Answer:"""
    
    def _extract_answer(self, text: str) -> str:
        text = text.strip()
        match = re.search(r"####\s*([\d.,+-]+)", text)
        if match:
            return match.group(1).replace(",", "")
        numbers = re.findall(r"[\d.,+-]+", text)
        return numbers[-1].replace(",", "") if numbers else ""


class NumericAnswerJudge:
    """Judge for numeric answer comparison."""
    
    def judge(self, predicted: str, expected: str, task: Dict, output: Any) -> Any:
        import time
        start = time.time()
        
        try:
            pred_val = float(predicted)
            exp_val = float(expected)
            passed = abs(pred_val - exp_val) < 1e-6
        except ValueError:
            passed = predicted.strip() == expected.strip()
        
        score = 1.0 if passed else 0.0
        exec_time = int((time.time() - start) * 1000)
        
        class Result:
            def __init__(self, score, raw_score, details, passed, execution_time_ms):
                self.score = score
                self.raw_score = raw_score
                self.details = details
                self.passed = passed
                self.execution_time_ms = execution_time_ms
        
        return Result(
            score, 
            {"predicted": predicted, "expected": expected}, 
            {"match": passed}, 
            passed, 
            exec_time
        )