"""Judge factory for creating judges from configuration."""

from typing import Any, Dict, Type, Union
from agent_eval.judges.base import BaseJudge, JudgeResult, LLMJudgeConfig
from agent_eval.judges.llm_judge import LLMJudge, EnsembleJudge
from agent_eval.plugins.benchmark.humaneval_plugin import CodeExecutionJudge
from agent_eval.plugins.benchmark.gsm8k_plugin import NumericAnswerJudge
from agent_eval.plugins.dynamic.tool_use_plugin import (
    ToolCorrectnessJudge, EfficiencyJudge, RobustnessJudge,
)
from agent_eval.plugins.dynamic.multi_turn_plugin import (
    ConversationQualityJudge, ContextRetentionJudge, ConsistencyJudge,
)
from agent_eval.plugins.dynamic.coding_plugin import (
    CodeCorrectnessJudge, CodeStyleJudge, CodeEfficiencyJudge,
)
from agent_eval.plugins.adversarial.jailbreak_plugin import SafetyClassifier, RefusalDetector
from agent_eval.plugins.adversarial.injection_plugin import InjectionDetectionJudge
from agent_eval.plugins.adversarial.bias_plugin import BiasDetectionJudge


class ScorerBridge(BaseJudge):
    """Bridge that wraps any Scorer as a BaseJudge for backward compatibility."""

    def __init__(self, scorer, name: str = ""):
        self._scorer = scorer
        self.name = name or getattr(scorer, "name", "scorer_bridge")
        self.description = getattr(scorer, "description", "")

    def score(self, task: Dict[str, Any], output: Any) -> float:
        result = self._scorer.score(
            output,
            task=task,
            expected=task.get("expected", ""),
            context=task.get("context", ""),
            input=task.get("input", task.get("prompt", "")),
        )
        return result.score

    def explain(self, task: Dict[str, Any], output: Any, score: float) -> str:
        return f"Scored: {score:.2f}"

    def judge(self, **kwargs) -> JudgeResult:
        import time
        start = time.time()
        out_str = str(kwargs.pop("output", ""))
        result = self._scorer.score(out_str, **kwargs)
        exec_time = int((time.time() - start) * 1000)
        return JudgeResult(
            score=result.score,
            raw_score={"scorer_score": result.score},
            details=result.metadata,
            passed=result.passed,
            execution_time_ms=exec_time,
            explanation=result.reason,
        )


class JudgeFactory:
    """Factory for creating judges from config dicts."""

    _registry: Dict[str, Union[Type[BaseJudge], type]] = {}

    @classmethod
    def register(cls, name: str, judge_class: type) -> None:
        cls._registry[name] = judge_class

    @classmethod
    def create(cls, config: Union[Dict[str, Any], BaseJudge]) -> Union[BaseJudge, Any]:
        if isinstance(config, BaseJudge):
            return config

        if not isinstance(config, dict):
            raise ValueError(f"Invalid judge config: {config}")

        judge_type = config.get("type", config.get("name", ""))

        if not judge_type:
            raise ValueError(f"Judge config missing 'type': {config}")

        if judge_type in cls._registry:
            return cls._registry[judge_type](**{k: v for k, v in config.items() if k not in ("type", "name")})

        registry = {
            "exact_match": cls._create_exact_match,
            "numeric_answer": cls._create_numeric_answer,
            "code_execution": cls._create_code_execution,
            "tool_correctness": cls._create_tool_correctness,
            "efficiency": cls._create_efficiency,
            "robustness": cls._create_robustness,
            "conversation_quality": cls._create_conversation_quality,
            "context_retention": cls._create_context_retention,
            "consistency": cls._create_consistency,
            "code_correctness": cls._create_code_correctness,
            "code_style": cls._create_code_style,
            "code_efficiency": cls._create_code_efficiency,
            "safety_classifier": cls._create_safety_classifier,
            "refusal_detection": cls._create_refusal_detection,
            "injection_detection": cls._create_injection_detection,
            "bias_detection": cls._create_bias_detection,
            "llm": cls._create_llm_judge,
            "ensemble": cls._create_ensemble,
            "multi_choice": cls._create_exact_match,
        }

        creator = registry.get(judge_type)
        if creator:
            return creator(config)

        # Try creating a Scorer (DeepEval-inspired metrics)
        try:
            from agent_eval.scorers.factory import ScorerFactory
            scorer = ScorerFactory.create(config)
            return ScorerBridge(scorer, name=judge_type)
        except (ValueError, ImportError):
            pass

        raise ValueError(f"Unknown judge type: '{judge_type}'. Available: {list(registry.keys()) + ScorerFactory.list_scorers().keys()}")

    @classmethod
    def _create_exact_match(cls, config: Dict) -> BaseJudge:
        class ExactMatchJudge(BaseJudge):
            name = "exact_match"
            description = "Exact string match judge"

            def score(self, task: Dict, output: Any) -> float:
                predicted = config.get("predicted_key", "predicted")
                expected = config.get("expected_key", "expected")
                p = task.get(predicted, "")
                e = task.get(expected, "")
                return 1.0 if str(p).strip() == str(e).strip() else 0.0

            def explain(self, task: Dict, output: Any, score: float) -> str:
                return f"Exact match: {score:.2f}"

        return ExactMatchJudge()

    @classmethod
    def _create_numeric_answer(cls, config: Dict) -> NumericAnswerJudge:
        return NumericAnswerJudge()

    @classmethod
    def _create_code_execution(cls, config: Dict) -> CodeExecutionJudge:
        return CodeExecutionJudge()

    @classmethod
    def _create_tool_correctness(cls, config: Dict) -> ToolCorrectnessJudge:
        return ToolCorrectnessJudge()

    @classmethod
    def _create_efficiency(cls, config: Dict) -> EfficiencyJudge:
        return EfficiencyJudge()

    @classmethod
    def _create_robustness(cls, config: Dict) -> RobustnessJudge:
        return RobustnessJudge()

    @classmethod
    def _create_conversation_quality(cls, config: Dict) -> ConversationQualityJudge:
        return ConversationQualityJudge()

    @classmethod
    def _create_context_retention(cls, config: Dict) -> ContextRetentionJudge:
        return ContextRetentionJudge()

    @classmethod
    def _create_consistency(cls, config: Dict) -> ConsistencyJudge:
        return ConsistencyJudge()

    @classmethod
    def _create_code_correctness(cls, config: Dict) -> CodeCorrectnessJudge:
        return CodeCorrectnessJudge()

    @classmethod
    def _create_code_style(cls, config: Dict) -> CodeStyleJudge:
        return CodeStyleJudge()

    @classmethod
    def _create_code_efficiency(cls, config: Dict) -> CodeEfficiencyJudge:
        return CodeEfficiencyJudge()

    @classmethod
    def _create_safety_classifier(cls, config: Dict) -> SafetyClassifier:
        return SafetyClassifier(models=config.get("models", ["gpt-4o"]), threshold=config.get("threshold", 0.5))

    @classmethod
    def _create_refusal_detection(cls, config: Dict) -> RefusalDetector:
        return RefusalDetector()

    @classmethod
    def _create_injection_detection(cls, config: Dict) -> InjectionDetectionJudge:
        return InjectionDetectionJudge()

    @classmethod
    def _create_bias_detection(cls, config: Dict) -> BiasDetectionJudge:
        return BiasDetectionJudge()

    @classmethod
    def _create_llm_judge(cls, config: Dict) -> LLMJudge:
        llm_config = LLMJudgeConfig(
            model=config.get("model", "gpt-4o-mini"),
            rubric=config.get("rubric", ""),
            few_shot_examples=config.get("few_shot_examples", []),
            use_cot=config.get("use_cot", True),
            n_samples=config.get("n_samples", 3),
            temperature=config.get("temperature", 0.0),
            max_tokens=config.get("max_tokens", 500),
        )
        return LLMJudge(llm_config)

    @classmethod
    def _create_ensemble(cls, config: Dict) -> EnsembleJudge:
        sub_judge_configs = config.get("judges", [])
        weights = config.get("weights", None)
        judges = [cls.create(jc) for jc in sub_judge_configs]
        return EnsembleJudge(judges, weights)