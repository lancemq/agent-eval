"""Tool Use Dynamic Evaluation Evaluator."""

import time
from typing import Any, Dict, List
from agent_eval.evaluators.base import BaseEvaluator, EvaluationType, EvalContext, EvalResult, register_evaluator
from agent_eval.utils import resolve_config_path


@register_evaluator
class ToolUseEvaluator(BaseEvaluator):
    name = "tool_use"
    version = "1.0"
    evaluation_type = EvaluationType.DYNAMIC
    supported_dimensions = ["tool_calling", "planning", "error_recovery", "efficiency"]
    description = "Dynamic tool use evaluation with sandbox environment"
    
    def __init__(self):
        super().__init__()
        self.scenarios = []
        self.env = None
        self.judge_panel = None
        self.max_turns = 10
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.max_turns = config.get("max_turns", 10)
        self.scenario_file = resolve_config_path(config.get("scenario_file", "scenarios/tool_use.yaml"), config)
        self.sandbox_type = config.get("sandbox", "local")
        self.sandbox_config = config.get("sandbox_config", {})
        self._load_scenarios()
        self._init_environment()
        self._init_judges(config.get("judges", []))
    
    def _load_scenarios(self) -> None:
        try:
            import yaml
            with open(self.scenario_file) as f:
                data = yaml.safe_load(f)
                self.scenarios = data.get("scenarios", [])
        except FileNotFoundError:
            self.scenarios = self._default_scenarios()
        except Exception as e:
            raise RuntimeError(f"Failed to load scenarios: {e}")
    
    def _default_scenarios(self) -> List[Dict]:
        return [
            {
                "task_id": "web_search_1",
                "goal": "Find the current temperature in San Francisco",
                "available_tools": ["web_search", "weather_api"],
                "initial_state": {},
                "success_criteria": {"must_call": ["weather_api"], "max_turns": 3},
            },
            {
                "task_id": "file_ops_1",
                "goal": "Create a file 'test.txt' with content 'Hello World' and read it back",
                "available_tools": ["file_write", "file_read"],
                "initial_state": {},
                "success_criteria": {"must_call": ["file_write", "file_read"], "max_turns": 4},
            },
            {
                "task_id": "calculation_1",
                "goal": "Calculate (15 * 23) + (42 / 6) using the calculator tool",
                "available_tools": ["calculator"],
                "initial_state": {},
                "success_criteria": {"must_call": ["calculator"], "expected_result": 82.0, "max_turns": 3},
            },
        ]
    
    def _init_environment(self) -> None:
        from agent_eval.sandbox.factory import SandboxFactory
        self.env = SandboxFactory.create(self.sandbox_type, self.sandbox_config)
        self.env.setup()

    def teardown(self) -> None:
        if self.env:
            self.env.teardown()
    
    def _init_judges(self, judge_configs: List[Dict]) -> None:
        from agent_eval.judges.panel import MultiJudgePanel
        from agent_eval.judges.factory import JudgeFactory
        
        judges = []
        for jc in judge_configs:
            judges.append(JudgeFactory.create(jc))
        
        if not judges:
            judges = [
                JudgeFactory.create({"type": "tool_correctness", "name": "tool_correctness"}),
                JudgeFactory.create({"type": "efficiency", "name": "efficiency"}),
                JudgeFactory.create({"type": "robustness", "name": "robustness"}),
            ]
        
        self.judge_panel = MultiJudgePanel(judges)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        return self.scenarios
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        trajectory = []
        state = task.get("initial_state", {}).copy()
        max_turns = task.get("success_criteria", {}).get("max_turns", self.max_turns)
        
        for turn in range(max_turns):
            action = context.agent_under_test.act(
                state=state,
                available_tools=task["available_tools"],
                goal=task["goal"]
            )
            
            step = {
                "turn": turn,
                "action": action,
                "state_before": state.copy(),
            }
            trajectory.append(step)
            
            if action.get("type") == "finish":
                step["state_after"] = state
                break
            
            result = self.env.execute(action)
            step["result"] = result
            state = result.get("new_state", state)
            step["state_after"] = state.copy()
            
            if result.get("error") and not task.get("allow_errors", False):
                break
        
        return {
            "trajectory": trajectory,
            "final_state": state,
            "task_id": task["task_id"],
            "goal": task["goal"],
        }
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        start = time.time()
        
        judge_result = self.judge_panel.evaluate(task, output)
        
        exec_time = int((time.time() - start) * 1000)
        
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=judge_result["_final"],
            raw_score=judge_result,
            details={
                "trajectory": output["trajectory"],
                "judge_scores": {k: v for k, v in judge_result.items() if not k.startswith("_")},
            },
            artifacts=[output["trajectory"]],
            passed=judge_result["_final"] >= task.get("threshold", 0.7),
            execution_time_ms=exec_time,
            task_id=task["task_id"]
        )


# Tool correctness judge
class ToolCorrectnessJudge:
    name = "tool_correctness"
    
    def score(self, task: Dict, output: Dict) -> float:
        trajectory = output.get("trajectory", [])
        if not trajectory:
            return 0.0
        
        success_criteria = task.get("success_criteria", {})
        required_tools = success_criteria.get("must_call", [])
        expected_result = success_criteria.get("expected_result")
        
        called_tools = []
        for step in trajectory:
            action = step.get("action", {})
            if action.get("type") == "tool_call":
                called_tools.append(action.get("tool"))
        
        if required_tools:
            missing = set(required_tools) - set(called_tools)
            if missing:
                return 0.5
        
        if expected_result is not None:
            final_result = None
            for step in reversed(trajectory):
                result = step.get("result", {})
                if result.get("output") is not None:
                    final_result = result.get("output")
                    break
            
            if final_result is not None:
                try:
                    if abs(float(final_result) - float(expected_result)) > 1e-6:
                        return 0.3
                except (ValueError, TypeError):
                    if str(final_result) != str(expected_result):
                        return 0.3
        
        return 1.0
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Tool correctness score: {score}"


# Efficiency judge
class EfficiencyJudge:
    name = "efficiency"
    
    def score(self, task: Dict, output: Dict) -> float:
        trajectory = output.get("trajectory", [])
        if not trajectory:
            return 0.0
        
        max_turns = task.get("success_criteria", {}).get("max_turns", 10)
        actual_turns = len([s for s in trajectory if s.get("action", {}).get("type") == "tool_call"])
        
        if actual_turns == 0:
            return 0.0

        return max(0.0, 1.0 - (actual_turns - max_turns) * 0.1) if actual_turns > max_turns else 1.0
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Efficiency score: {score}"


# Robustness judge
class RobustnessJudge:
    name = "robustness"
    
    def score(self, task: Dict, output: Dict) -> float:
        trajectory = output.get("trajectory", [])
        if not trajectory:
            return 0.0
        
        error_count = sum(1 for s in trajectory if s.get("result", {}).get("error"))
        total_tool_calls = sum(1 for s in trajectory if s.get("action", {}).get("type") == "tool_call")
        
        if total_tool_calls == 0:
            return 0.0
        
        error_rate = error_count / total_tool_calls
        return max(0.0, 1.0 - error_rate * 2)
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Robustness score: {score}"
