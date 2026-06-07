"""Scorers package - comprehensive scoring tools for LLM evaluation.

Inspired by DeepEval, RAGAS, and modern LLM evaluation frameworks.
Provides 28+ built-in scorers across 6 categories."""

from agent_eval.scorers.base import BaseScorer, ScorerResult
from agent_eval.scorers.factory import ScorerFactory, scorer

from agent_eval.scorers.g_eval import GEvalScorer, SummarizationScorer
from agent_eval.scorers.faithfulness import FaithfulnessScorer, HallucinationScorer, AnswerCorrectnessScorer
from agent_eval.scorers.relevancy import (
    AnswerRelevancyScorer, ContextualRelevancyScorer,
    ContextualRecallScorer, ContextualPrecisionScorer,
)
from agent_eval.scorers.safety import ToxicityScorer, BiasScorer, SafetyScorer
from agent_eval.scorers.deterministic import (
    ExactMatchScorer, NumericMatchScorer, RegexScorer, JSONScorer,
    KeywordScorer, LengthScorer, ContainsAnyScorer, ContainsAllScorer,
    CustomRubricScorer,
)
from agent_eval.scorers.agent import (
    TaskCompletionScorer, ToolCallCorrectnessScorer,
    ConversationQualityScorer, RoleAdherenceScorer, TaskEfficiencyScorer,
)
from agent_eval.scorers.ensemble import EnsembleScorer, ThresholdScorer

__all__ = [
    "BaseScorer", "ScorerResult", "ScorerFactory", "scorer",
    "GEvalScorer", "SummarizationScorer",
    "FaithfulnessScorer", "HallucinationScorer", "AnswerCorrectnessScorer",
    "AnswerRelevancyScorer", "ContextualRelevancyScorer",
    "ContextualRecallScorer", "ContextualPrecisionScorer",
    "ToxicityScorer", "BiasScorer", "SafetyScorer",
    "ExactMatchScorer", "NumericMatchScorer", "RegexScorer", "JSONScorer",
    "KeywordScorer", "LengthScorer", "ContainsAnyScorer", "ContainsAllScorer",
    "CustomRubricScorer",
    "TaskCompletionScorer", "ToolCallCorrectnessScorer",
    "ConversationQualityScorer", "RoleAdherenceScorer", "TaskEfficiencyScorer",
    "EnsembleScorer", "ThresholdScorer",
]

# Import to trigger registration
_scorer_types = [k for k in __all__ if k not in ("BaseScorer", "ScorerResult", "ScorerFactory")]