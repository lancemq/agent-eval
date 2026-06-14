"""Scorer factory for creating scorers from configuration."""

from typing import Any, Dict, Type, Union
from agent_eval.scorers.base import BaseScorer

# Import all scorers to register them
from agent_eval.scorers.g_eval import GEvalScorer, SummarizationScorer
from agent_eval.scorers.faithfulness import FaithfulnessScorer, HallucinationScorer, AnswerCorrectnessScorer
from agent_eval.scorers.relevancy import AnswerRelevancyScorer, ContextualRelevancyScorer, ContextualRecallScorer, ContextualPrecisionScorer
from agent_eval.scorers.safety import ToxicityScorer, BiasScorer, SafetyScorer
from agent_eval.scorers.deterministic import (
    ExactMatchScorer, NumericMatchScorer, RegexScorer, JSONScorer,
    KeywordScorer, LengthScorer, ContainsAnyScorer, ContainsAllScorer, CustomRubricScorer,
)
from agent_eval.scorers.agent import (
    TaskCompletionScorer, ToolCallCorrectnessScorer,
    ConversationQualityScorer, RoleAdherenceScorer, TaskEfficiencyScorer,
)
from agent_eval.scorers.ensemble import EnsembleScorer, ThresholdScorer


def scorer(name: str):
    """Decorator to register a custom scorer class.
    
    Usage:
        @scorer("my_custom_scorer")
        class MyCustomScorer(BaseScorer):
            def score(self, output: str, **kwargs) -> ScorerResult:
                ...
    """
    def decorator(cls: Type[BaseScorer]) -> Type[BaseScorer]:
        ScorerFactory.register(name, cls)
        return cls
    return decorator


class ScorerFactory:
    """Creates scorer instances from configuration dicts."""

    _registry: Dict[str, Type[BaseScorer]] = {}

    @classmethod
    def register(cls, name: str, scorer_class: Type[BaseScorer]) -> None:
        cls._registry[name] = scorer_class

    @classmethod
    def create(cls, config: Union[str, Dict[str, Any], BaseScorer]) -> BaseScorer:
        if isinstance(config, BaseScorer):
            return config
        if isinstance(config, str):
            config = {"type": config}
        if not isinstance(config, dict):
            raise ValueError(f"Invalid scorer config: {config}")

        scorer_type = config.get("type", config.get("name", ""))
        if not scorer_type:
            raise ValueError(f"Scorer config missing 'type': {config}")

        if scorer_type in cls._registry:
            scorer_cls = cls._registry[scorer_type]
            params = {k: v for k, v in config.items() if k not in ("type", "name")}
            return scorer_cls(**params)

        # Built-in name-based lookup
        name_map = {
            "g_eval": GEvalScorer,
            "summarization": SummarizationScorer,
            "faithfulness": FaithfulnessScorer,
            "hallucination": HallucinationScorer,
            "answer_correctness": AnswerCorrectnessScorer,
            "answer_relevancy": AnswerRelevancyScorer,
            "contextual_relevancy": ContextualRelevancyScorer,
            "contextual_recall": ContextualRecallScorer,
            "contextual_precision": ContextualPrecisionScorer,
            "toxicity": ToxicityScorer,
            "bias": BiasScorer,
            "safety": SafetyScorer,
            "exact_match": ExactMatchScorer,
            "numeric_match": NumericMatchScorer,
            "regex_match": RegexScorer,
            "json_valid": JSONScorer,
            "keyword": KeywordScorer,
            "length": LengthScorer,
            "contains_any": ContainsAnyScorer,
            "contains_all": ContainsAllScorer,
            "custom_rubric": CustomRubricScorer,
            "task_completion": TaskCompletionScorer,
            "tool_call_correctness": ToolCallCorrectnessScorer,
            "conversation_quality": ConversationQualityScorer,
            "role_adherence": RoleAdherenceScorer,
            "task_efficiency": TaskEfficiencyScorer,
            "ensemble": EnsembleScorer,
            "threshold": ThresholdScorer,
        }

        scorer_cls = name_map.get(scorer_type)
        if scorer_cls is None:
            raise ValueError(
                f"Unknown scorer type: '{scorer_type}'. "
                f"Available: {list(name_map.keys())}"
            )

        params = {k: v for k, v in config.items() if k not in ("type", "name")}
        return scorer_cls(**params)

    @classmethod
    def list_scorers(cls) -> Dict[str, str]:
        return {
            "g_eval": "General-purpose LLM evaluation with chain-of-thought",
            "summarization": "Summary quality (coverage, conciseness, coherence)",
            "faithfulness": "Output faithfulness to context (no contradictions)",
            "hallucination": "Hallucination detection relative to context",
            "answer_correctness": "Answer correctness against expected output",
            "answer_relevancy": "Relevancy of answer to input query",
            "contextual_relevancy": "Relevancy of retrieval context to query",
            "contextual_recall": "Whether context supports the expected answer",
            "contextual_precision": "Whether relevant docs ranked higher",
            "toxicity": "Toxic/harmful content detection",
            "bias": "Demographic/social bias detection",
            "safety": "Combined safety (toxicity + bias)",
            "exact_match": "Exact string or numeric match",
            "numeric_match": "Numeric comparison with tolerance",
            "regex_match": "Regex pattern matching",
            "json_valid": "JSON structure validation",
            "keyword": "Keyword presence/absence check",
            "length": "Length constraints (chars/words)",
            "contains_any": "Contains any of given strings",
            "contains_all": "Contains all given strings",
            "custom_rubric": "Custom rubric evaluation",
            "task_completion": "Multi-step task completion",
            "tool_call_correctness": "Tool selection and parameter accuracy",
            "conversation_quality": "Multi-turn conversation quality",
            "role_adherence": "Persona/role adherence",
            "task_efficiency": "Task completion efficiency (steps)",
            "ensemble": "Combine multiple scorers",
            "threshold": "Threshold wrapper for any scorer",
        }


# Register all scorers
ScorerFactory.register("g_eval", GEvalScorer)
ScorerFactory.register("summarization", SummarizationScorer)
ScorerFactory.register("faithfulness", FaithfulnessScorer)
ScorerFactory.register("hallucination", HallucinationScorer)
ScorerFactory.register("answer_correctness", AnswerCorrectnessScorer)
ScorerFactory.register("answer_relevancy", AnswerRelevancyScorer)
ScorerFactory.register("contextual_relevancy", ContextualRelevancyScorer)
ScorerFactory.register("contextual_recall", ContextualRecallScorer)
ScorerFactory.register("contextual_precision", ContextualPrecisionScorer)
ScorerFactory.register("toxicity", ToxicityScorer)
ScorerFactory.register("bias", BiasScorer)
ScorerFactory.register("safety", SafetyScorer)
ScorerFactory.register("exact_match", ExactMatchScorer)
ScorerFactory.register("numeric_match", NumericMatchScorer)
ScorerFactory.register("regex_match", RegexScorer)
ScorerFactory.register("json_valid", JSONScorer)
ScorerFactory.register("keyword", KeywordScorer)
ScorerFactory.register("length", LengthScorer)
ScorerFactory.register("contains_any", ContainsAnyScorer)
ScorerFactory.register("contains_all", ContainsAllScorer)
ScorerFactory.register("custom_rubric", CustomRubricScorer)
ScorerFactory.register("task_completion", TaskCompletionScorer)
ScorerFactory.register("tool_call_correctness", ToolCallCorrectnessScorer)
ScorerFactory.register("conversation_quality", ConversationQualityScorer)
ScorerFactory.register("role_adherence", RoleAdherenceScorer)
ScorerFactory.register("task_efficiency", TaskEfficiencyScorer)
ScorerFactory.register("ensemble", EnsembleScorer)
ScorerFactory.register("threshold", ThresholdScorer)