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
from agent_eval.scorers.similarity import (
    BLEUScorer, ROUGEScorer, F1TokenScorer, EditDistanceScorer,
    JaccardScorer, CosineSimilarityScorer, SemanticSimilarityScorer,
)
from agent_eval.scorers.code_quality import (
    CodeQualityScorer, SQLValidationScorer, CodeFormatScorer,
    CyclomaticComplexityScorer, CodeSecurityScorer,
)
from agent_eval.scorers.text_analysis import (
    ReadabilityScorer, LexicalDiversityScorer, SentimentScorer,
    GrammarCheckScorer, ToneAnalyzerScorer, CoherenceScorer, FluencyScorer,
)
from agent_eval.scorers.format_validation import (
    DateTimeFormatScorer, URLFormatScorer, EmailFormatScorer,
    MarkdownStructureScorer, CitationCheckScorer, InstructionFollowingScorer,
)
from agent_eval.scorers.metrics import (
    ClassificationMetricsScorer, RegressionMetricsScorer, RankingMetricsScorer,
)

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
    # Similarity
    "BLEUScorer", "ROUGEScorer", "F1TokenScorer", "EditDistanceScorer",
    "JaccardScorer", "CosineSimilarityScorer", "SemanticSimilarityScorer",
    # Code quality
    "CodeQualityScorer", "SQLValidationScorer", "CodeFormatScorer",
    "CyclomaticComplexityScorer", "CodeSecurityScorer",
    # Text analysis
    "ReadabilityScorer", "LexicalDiversityScorer", "SentimentScorer",
    "GrammarCheckScorer", "ToneAnalyzerScorer", "CoherenceScorer", "FluencyScorer",
    # Format validation
    "DateTimeFormatScorer", "URLFormatScorer", "EmailFormatScorer",
    "MarkdownStructureScorer", "CitationCheckScorer", "InstructionFollowingScorer",
    # ML metrics
    "ClassificationMetricsScorer", "RegressionMetricsScorer", "RankingMetricsScorer",
]

# Import to trigger registration
_scorer_types = [k for k in __all__ if k not in ("BaseScorer", "ScorerResult", "ScorerFactory")]