"""Coding Task Dynamic Evaluation Evaluator."""

import tempfile
import subprocess
import os
from typing import Any, Dict, List
from agent_eval.evaluators.base import BaseEvaluator, EvaluationType, EvalContext, EvalResult, register_evaluator
from agent_eval.utils import resolve_config_path


@register_evaluator
class CodingEvaluator(BaseEvaluator):
    name = "coding"
    version = "1.0"
    evaluation_type = EvaluationType.DYNAMIC
    supported_dimensions = ["code_generation", "debugging", "refactoring", "testing", "problem_solving"]
    description = "Dynamic coding task evaluation with execution"
    
    def __init__(self):
        super().__init__()
        self.tasks = []
        self.judge_panel = None
        self.timeout = 30
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.timeout = config.get("timeout", 30)
        self.task_file = resolve_config_path(config.get("task_file", "scenarios/coding.yaml"), config)
        self._load_tasks()
        self._init_judges(config.get("judges", []))
    
    def _load_tasks(self) -> None:
        try:
            import yaml
            with open(self.task_file) as f:
                data = yaml.safe_load(f)
                self.tasks = data.get("tasks", [])
        except FileNotFoundError:
            self.tasks = self._default_tasks()
        except Exception as e:
            raise RuntimeError(f"Failed to load coding tasks: {e}")
    
    def _default_tasks(self) -> List[Dict]:
        return [
            {
                "task_id": "coding_1",
                "type": "generation",
                "prompt": "Write a Python function to find the longest common subsequence of two strings.",
                "entry_point": "longest_common_subsequence",
                "test_cases": [
                    {"input": ("ABCDGH", "AEDFHR"), "expected": "ADH"},
                    {"input": ("AGGTAB", "GXTXAYB"), "expected": "GTAB"},
                ],
                "criteria": {"correctness": 0.6, "efficiency": 0.2, "style": 0.2},
            },
            {
                "task_id": "coding_2",
                "type": "debugging",
                "prompt": "Fix the bug in this code:\n\n```python\ndef find_max(nums):\n    max_val = 0\n    for n in nums:\n        if n > max_val:\n            max_val = n\n    return max_val\n```",
                "entry_point": "find_max",
                "test_cases": [
                    {"input": ([1, 5, 3, 9, 2],), "expected": 9},
                    {"input": ([-5, -1, -3],), "expected": -1},
                    {"input": ([],), "expected": None},
                ],
                "criteria": {"correctness": 0.7, "explanation": 0.3},
            },
            {
                "task_id": "coding_3",
                "type": "refactoring",
                "prompt": "Refactor this code to be more Pythonic and efficient:\n\n```python\ndef process_items(items):\n    result = []\n    for i in range(len(items)):\n        if items[i] % 2 == 0:\n            result.append(items[i] * 2)\n    return result\n```",
                "entry_point": "process_items",
                "test_cases": [
                    {"input": ([1, 2, 3, 4, 5],), "expected": [4, 8]},
                    {"input": ([],), "expected": []},
                ],
                "criteria": {"correctness": 0.4, "style": 0.4, "efficiency": 0.2},
            },
        ]
    
    def _init_judges(self, judge_configs: List[Dict]) -> None:
        from agent_eval.judges.panel import MultiJudgePanel
        from agent_eval.judges.factory import JudgeFactory
        
        judges = []
        for jc in judge_configs:
            judges.append(JudgeFactory.create(jc))
        
        if not judges:
            judges = [
                JudgeFactory.create({"type": "code_correctness", "name": "correctness"}),
                JudgeFactory.create({"type": "code_style", "name": "style"}),
                JudgeFactory.create({"type": "code_efficiency", "name": "efficiency"}),
            ]
        
        self.judge_panel = MultiJudgePanel(judges)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        return self.tasks
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        prompt = task["prompt"]
        response = context.agent_under_test.generate(prompt)
        code = self._extract_code(response)
        
        test_results = []
        for tc in task.get("test_cases", []):
            tc = {**tc, "entry_point": tc.get("entry_point", task.get("entry_point", "solution"))}
            result = self._run_test(code, tc)
            test_results.append(result)
        
        return {
            "code": code,
            "response": response,
            "test_results": test_results,
            "task_id": task["task_id"],
            "task_type": task.get("type", "generation"),
            "entry_point": task.get("entry_point"),
            "criteria": task.get("criteria", {}),
        }
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        import time
        start = time.time()
        
        judge_result = self.judge_panel.evaluate(task, output)
        
        exec_time = int((time.time() - start) * 1000)
        
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=judge_result["_final"],
            raw_score=judge_result,
            details={
                "code": output["code"],
                "test_results": output["test_results"],
                "judge_scores": {k: v for k, v in judge_result.items() if not k.startswith("_")},
            },
            artifacts=[output["code"], output["test_results"]],
            passed=judge_result["_final"] >= 0.7,
            execution_time_ms=exec_time,
            task_id=task["task_id"]
        )
    
    def _extract_code(self, response: str) -> str:
        import re
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()
        return response.strip()
    
    def _run_test(self, code: str, test_case: Dict) -> Dict:
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                f.write("\n\n")
                
                input_args = test_case["input"]
                if isinstance(input_args, tuple):
                    args_str = ", ".join(repr(a) for a in input_args)
                else:
                    args_str = repr(input_args)
                
                entry_point = test_case.get("entry_point") or "solution"
                f.write(f"result = {entry_point}({args_str})\n")
                f.write("print(repr(result))\n")
                temp_file = f.name
            
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            os.unlink(temp_file)
            
            if result.returncode == 0:
                actual = result.stdout.strip()
                expected = repr(test_case["expected"])
                passed = actual == expected
                return {
                    "passed": passed,
                    "actual": actual,
                    "expected": expected,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            else:
                return {
                    "passed": False,
                    "error": result.stderr,
                    "stdout": result.stdout,
                }
        except subprocess.TimeoutExpired:
            return {"passed": False, "error": "timeout"}
        except Exception as e:
            return {"passed": False, "error": str(e)}


class CodeCorrectnessJudge:
    name = "correctness"
    
    def score(self, task: Dict, output: Dict) -> float:
        test_results = output.get("test_results", [])
        if not test_results:
            return 0.0
        
        passed = sum(1 for tr in test_results if tr.get("passed"))
        return passed / len(test_results)
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Code correctness: {score:.2f}"


class CodeStyleJudge:
    name = "style"
    
    def score(self, task: Dict, output: Dict) -> float:
        code = output.get("code", "")
        if not code:
            return 0.0
        
        score = 1.0
        issues = []
        
        lines = code.split("\n")
        for line in lines:
            if len(line) > 100:
                score -= 0.05
                issues.append("line_too_long")
        
        if "def " in code and '"""' not in code and "'''" not in code:
            score -= 0.1
            issues.append("missing_docstring")
        
        import re
        if re.search(r"\b(l|I|O)\b", code):
            score -= 0.05
            issues.append("single_letter_vars")
        
        return max(0.0, score)
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Code style: {score:.2f}"


class CodeEfficiencyJudge:
    name = "efficiency"
    
    def score(self, task: Dict, output: Dict) -> float:
        code = output.get("code", "")
        if not code:
            return 0.0
        
        score = 1.0
        
        if "for " in code and "in range(len(" in code:
            score -= 0.2
        
        if code.count("for ") > 2:
            score -= 0.1
        
        if "while " in code and "for " in code:
            score -= 0.05
        
        return max(0.0, score)
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Code efficiency: {score:.2f}"
