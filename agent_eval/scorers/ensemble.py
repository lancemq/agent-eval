"""Ensemble scorer that combines multiple scorers."""

import statistics
from typing import Dict, List, Optional, Union
from agent_eval.scorers.base import BaseScorer, ScorerResult


class EnsembleScorer(BaseScorer):
    """Combines multiple scorers with configurable aggregation.

    Supports: weighted average, median, min, max, majority vote.
    """

    name = "ensemble"
    description = "Combines multiple scorers with configurable aggregation"

    def __init__(
        self,
        scorers: List[Union[BaseScorer, Dict]],
        aggregation: str = "weighted",
        weights: Optional[List[float]] = None,
        threshold: float = 0.5,
    ):
        self.scorers = []
        for s in scorers:
            if isinstance(s, BaseScorer):
                self.scorers.append(s)
            elif isinstance(s, dict):
                from agent_eval.scorers.factory import ScorerFactory
                self.scorers.append(ScorerFactory.create(s))
            else:
                raise ValueError(f"Invalid scorer config: {s}")

        self.aggregation = aggregation
        n = len(self.scorers)
        self.weights = [1.0 / n] * n if weights is None else weights
        if len(self.weights) != n:
            raise ValueError(f"Number of weights ({len(self.weights)}) must match scorers ({n})")
        self.threshold = threshold

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        results = []
        details = {}

        for scorer in self.scorers:
            try:
                r = scorer.score(output, **kwargs)
                results.append(r)
                details[scorer.name] = r.to_dict()
            except Exception as e:
                results.append(ScorerResult(name=getattr(scorer, "name", "error"), score=0.0, reason=str(e), passed=False))
                details[getattr(scorer, "name", "error")] = {"error": str(e)}

        scores = [r.score for r in results]

        if self.aggregation == "weighted":
            final_score = sum(s * w for s, w in zip(scores, self.weights)) / sum(self.weights)
        elif self.aggregation == "median":
            final_score = statistics.median(scores)
        elif self.aggregation == "min":
            final_score = min(scores)
        elif self.aggregation == "max":
            final_score = max(scores)
        elif self.aggregation == "mean":
            final_score = statistics.mean(scores)
        elif self.aggregation == "majority":
            passed_count = sum(1 for r in results if r.passed)
            final_score = 1.0 if passed_count > len(results) / 2 else 0.0
        else:
            final_score = statistics.mean(scores)

        reasons = [r.reason for r in results if r.reason]
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=min(final_score, 1.0),
            reason=" | ".join(reasons[:3]) if reasons else "Ensemble evaluation",
            passed=final_score >= self.threshold,
            metadata={
                "aggregation": self.aggregation,
                "individual_scores": {r.name: r.score for r in results},
                "details": details,
            },
            execution_time_ms=elapsed,
        )


class ThresholdScorer(BaseScorer):
    """Wraps a scorer and applies a pass/fail threshold."""

    name = "threshold"
    description = "Wraps a scorer with a custom pass/fail threshold"

    def __init__(self, scorer: Union[BaseScorer, Dict], threshold: float = 0.7):
        if isinstance(scorer, BaseScorer):
            self.inner = scorer
        else:
            from agent_eval.scorers.factory import ScorerFactory
            self.inner = ScorerFactory.create(scorer)
        self.pass_threshold = threshold

    def score(self, output: str, **kwargs) -> ScorerResult:
        result = self.inner.score(output, **kwargs)
        result.passed = result.score >= self.pass_threshold
        if not result.passed:
            result.reason = f"Score {result.score:.2f} below threshold {self.pass_threshold}. " + result.reason
        return result