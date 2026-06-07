"""Base classes for judges."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass
class JudgeResult:
    """Result from a judge evaluation."""
    score: float
    raw_score: Any
    details: Dict[str, Any]
    passed: bool
    execution_time_ms: int
    explanation: str = ""


class BaseJudge(ABC):
    """Base class for all judges."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def score(self, task: Dict[str, Any], output: Any) -> float:
        """Score a task output. Returns 0-1."""
        pass
    
    @abstractmethod
    def explain(self, task: Dict[str, Any], output: Any, score: float) -> str:
        """Explain the score."""
        pass
    
    def judge(self, **kwargs) -> JudgeResult:
        """Unified judge interface for plugins that use direct judging."""
        import time
        start = time.time()
        
        score = self.score(kwargs.get("task", {}), kwargs.get("output", {}))
        explanation = self.explain(kwargs.get("task", {}), kwargs.get("output", {}), score)
        
        exec_time = int((time.time() - start) * 1000)
        
        return JudgeResult(
            score=score,
            raw_score={"score": score},
            details={},
            passed=score >= 0.5,
            execution_time_ms=exec_time,
            explanation=explanation
        )


class LLMJudgeConfig:
    """Configuration for LLM-based judges."""
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        rubric: str = "",
        few_shot_examples: List[Dict] = None,
        use_cot: bool = True,
        n_samples: int = 3,
        temperature: float = 0.0,
        max_tokens: int = 500,
    ):
        self.model = model
        self.rubric = rubric
        self.few_shot_examples = few_shot_examples or []
        self.use_cot = use_cot
        self.n_samples = n_samples
        self.temperature = temperature
        self.max_tokens = max_tokens