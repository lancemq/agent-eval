"""HumanEval Benchmark Evaluator for code generation."""

import subprocess
import tempfile
import os
from typing import Any, Dict, List
from agent_eval.evaluators.base import BaseEvaluator, EvaluationType, EvalContext, EvalResult, register_evaluator


@register_evaluator
class HumanEvalEvaluator(BaseEvaluator):
    name = "humaneval"
    version = "1.0"
    evaluation_type = EvaluationType.BENCHMARK
    supported_dimensions = ["code_generation", "correctness", "reasoning"]
    description = "HumanEval code generation benchmark"
    
    def __init__(self):
        super().__init__()
        self.dataset = None
        self.timeout = 30
        self.judge = None
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.timeout = config.get("timeout", 30)
        self.judge_config = config.get("judge", {"type": "code_execution"})
        self._load_dataset()
        self._init_judge()
    
    def _load_dataset(self) -> None:
        try:
            from datasets import load_dataset
            self.dataset = load_dataset("openai_humaneval", split="test")
        except ImportError:
            raise RuntimeError("datasets library required: pip install datasets")
        except Exception as e:
            raise RuntimeError(f"Failed to load HumanEval dataset: {e}")
    
    def _init_judge(self) -> None:
        from agent_eval.judges.factory import JudgeFactory
        self.judge = JudgeFactory.create(self.judge_config)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        tasks = []
        for row in self.dataset:
            tasks.append({
                "task_id": row["task_id"],
                "prompt": row["prompt"],
                "canonical_solution": row["canonical_solution"],
                "test": row["test"],
                "entry_point": row["entry_point"],
            })
        return tasks
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        prompt = task["prompt"]
        response = context.agent_under_test.generate(prompt)
        code = self._extract_code(response)
        return {"code": code, "response": response, "prompt": prompt}
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        result = self.judge.judge(
            generated_code=output["code"],
            test_code=task["test"],
            entry_point=task["entry_point"],
            timeout=self.timeout
        )
        
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=result.score,
            raw_score=result.raw_score,
            details=result.details,
            artifacts=[output["code"], output["response"]],
            passed=result.passed,
            execution_time_ms=result.execution_time_ms,
            task_id=task["task_id"]
        )
    
    def _extract_code(self, response: str) -> str:
        import re
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()
        return response.strip()


class CodeExecutionJudge:
    """Judge that executes code and runs tests."""
    
    def judge(self, generated_code: str, test_code: str, entry_point: str, timeout: int) -> Any:
        import time
        start = time.time()
        
        full_code = f"{generated_code}\n\n{test_code}"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(full_code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            passed = result.returncode == 0
            score = 1.0 if passed else 0.0
            details = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            score = 0.0
            passed = False
            details = {"error": "timeout"}
        except Exception as e:
            score = 0.0
            passed = False
            details = {"error": str(e)}
        finally:
            os.unlink(temp_file)
        
        exec_time = int((time.time() - start) * 1000)
        
        class Result:
            def __init__(self, score, raw_score, details, passed, execution_time_ms):
                self.score = score
                self.raw_score = raw_score
                self.details = details
                self.passed = passed
                self.execution_time_ms = execution_time_ms
        
        return Result(score, {"passed": passed}, details, passed, exec_time)