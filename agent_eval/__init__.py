"""AgentEval - A pluggable evaluation framework for AI agents."""

from agent_eval.plugins.base import (
    BasePlugin,
    EvaluationType,
    EvalContext,
    EvalResult,
    register_plugin,
    PluginRegistry,
)
from agent_eval.orchestrator import EvaluationOrchestrator
from agent_eval.judges.base import BaseJudge
from agent_eval.judges.llm_judge import LLMJudge
from agent_eval.judges.panel import MultiJudgePanel
from agent_eval.judges.factory import ScorerBridge
from agent_eval.config import load_config, EvaluationConfig, OrchestratorConfig

# Expose scorers at top level
from agent_eval.scorers import (
    BaseScorer,
    ScorerResult,
    ScorerFactory,
    scorer,
    GEvalScorer,
    FaithfulnessScorer,
    HallucinationScorer,
    AnswerCorrectnessScorer,
    AnswerRelevancyScorer,
    ToxicityScorer,
    BiasScorer,
    SafetyScorer,
    ExactMatchScorer,
    JSONScorer,
    KeywordScorer,
    RegexScorer,
    CustomRubricScorer,
    EnsembleScorer,
)

# Expose universal agent integration
from agent_eval.agents import (
    AgentFactory,
    AgentProtocol,
    AgentAdapter,
    FunctionAgent,
    HTTPAgentAdapter,
    LangChainAdapter,
    AutoGenAdapter,
    CrewAIAdapter,
    LangGraphAdapter,
    agent_type,
)

# Trace system
from agent_eval.trace import (
    TraceRecord,
    TraceStore,
    TraceCollector,
    TraceAnalyzer,
    TracePlayer,
    TaskGenerator,
    DatasetBuilder,
)

__version__ = "0.1.0"

__all__ = [
    "BasePlugin",
    "EvaluationType",
    "EvalContext",
    "EvalResult",
    "register_plugin",
    "PluginRegistry",
    "EvaluationOrchestrator",
    "OrchestratorConfig",
    "BaseJudge",
    "LLMJudge",
    "MultiJudgePanel",
    "ScorerBridge",
    "load_config",
    "EvaluationConfig",
    "BaseScorer",
    "ScorerResult",
    "ScorerFactory",
    "scorer",
    "GEvalScorer",
    "FaithfulnessScorer",
    "HallucinationScorer",
    "AnswerCorrectnessScorer",
    "AnswerRelevancyScorer",
    "ToxicityScorer",
    "BiasScorer",
    "SafetyScorer",
    "ExactMatchScorer",
    "JSONScorer",
    "KeywordScorer",
    "RegexScorer",
    "CustomRubricScorer",
    "EnsembleScorer",
    # Agent integration
    "AgentFactory",
    "AgentProtocol",
    "AgentAdapter",
    "FunctionAgent",
    "HTTPAgentAdapter",
    "LangChainAdapter",
    "AutoGenAdapter",
    "CrewAIAdapter",
    "LangGraphAdapter",
    "agent_type",
    # Trace system
    "TraceRecord",
    "TraceStore",
    "TraceCollector",
    "TraceAnalyzer",
    "TracePlayer",
    "TaskGenerator",
    "DatasetBuilder",
]