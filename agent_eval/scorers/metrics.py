"""ML metric scorers: classification (P/R/F1), regression (MAE/MSE/RMSE/R²), ranking (NDCG/MRR)."""

from __future__ import annotations

import math
from typing import Any, Dict, List
from agent_eval.scorers.base import BaseScorer, ScorerResult


class ClassificationMetricsScorer(BaseScorer):
    """Evaluates classification predictions with precision, recall, F1, accuracy.

    Supports binary and multi-class classification. Output and expected
    can be labels (strings) or label lists.
    """

    name = "classification_metrics"
    description = "Classification metrics: precision, recall, F1, accuracy"

    def __init__(self, average: str = "macro"):
        self.average = average  # "macro", "micro", "weighted"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", kwargs.get("labels", ""))

        # Parse predictions and labels
        predictions = self._parse_labels(output)
        references = self._parse_labels(expected)

        if not predictions or not references:
            return ScorerResult(name=self.name, score=0.0, reason="No predictions/labels", passed=False)

        if len(predictions) != len(references):
            return ScorerResult(name=self.name, score=0.0,
                                reason=f"Length mismatch: {len(predictions)} vs {len(references)}", passed=False)

        labels = sorted(set(predictions) | set(references))
        per_label: Dict[str, Dict[str, float]] = {}

        for label in labels:
            tp = sum(1 for p, r in zip(predictions, references) if p == label and r == label)
            fp = sum(1 for p, r in zip(predictions, references) if p == label and r != label)
            fn = sum(1 for p, r in zip(predictions, references) if p != label and r == label)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            per_label[label] = {"precision": precision, "recall": recall, "f1": f1}

        # Accuracy
        correct = sum(1 for p, r in zip(predictions, references) if p == r)
        accuracy = correct / len(predictions)

        # Averaged F1
        if self.average == "macro":
            avg_f1 = sum(m["f1"] for m in per_label.values()) / len(per_label) if per_label else 0.0
        elif self.average == "micro":
            avg_f1 = accuracy  # micro F1 = accuracy for single-label
        else:
            avg_f1 = accuracy

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(avg_f1, 4),
            reason=f"Accuracy: {accuracy:.3f}, {self.average} F1: {avg_f1:.3f}",
            passed=avg_f1 >= kwargs.get("threshold", 0.5),
            metadata={
                "accuracy": round(accuracy, 4),
                f"{self.average}_f1": round(avg_f1, 4),
                "per_label": {k: {m: round(v, 4) for m, v in d.items()} for k, d in per_label.items()},
                "num_samples": len(predictions),
                "num_labels": len(labels),
            },
            execution_time_ms=elapsed,
        )

    @staticmethod
    def _parse_labels(data: Any) -> List[str]:
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, str):
            import json
            stripped = data.strip()
            # Try JSON list
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    return [str(x) for x in parsed]
                except json.JSONDecodeError:
                    pass
            # Comma-separated
            return [s.strip() for s in stripped.split(",") if s.strip()]
        return [str(data)]


class RegressionMetricsScorer(BaseScorer):
    """Evaluates regression predictions with MAE, MSE, RMSE, R².

    Output and expected should contain numeric values.
    """

    name = "regression_metrics"
    description = "Regression metrics: MAE, MSE, RMSE, R²"

    def __init__(self, metric: str = "r2"):
        self.metric = metric.lower()

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")

        predictions = self._parse_numbers(output)
        references = self._parse_numbers(expected)

        if not predictions or not references:
            return ScorerResult(name=self.name, score=0.0, reason="No values", passed=False)
        if len(predictions) != len(references):
            return ScorerResult(name=self.name, score=0.0,
                                reason=f"Length mismatch: {len(predictions)} vs {len(references)}", passed=False)

        n = len(predictions)
        mae = sum(abs(p - r) for p, r in zip(predictions, references)) / n
        mse = sum((p - r) ** 2 for p, r in zip(predictions, references)) / n
        rmse = math.sqrt(mse)

        mean_ref = sum(references) / n
        ss_res = sum((p - r) ** 2 for p, r in zip(predictions, references))
        ss_tot = sum((r - mean_ref) ** 2 for r in references)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # Use specified metric for the score
        if self.metric == "r2":
            score = max(0.0, min(1.0, r2))
        elif self.metric == "mae":
            score = max(0.0, 1.0 - mae / max(abs(mean_ref), 1e-10))
        elif self.metric == "rmse":
            score = max(0.0, 1.0 - rmse / max(abs(mean_ref), 1e-10))
        else:
            score = max(0.0, r2)

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"MAE={mae:.4f} MSE={mse:.4f} RMSE={rmse:.4f} R²={r2:.4f}",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"mae": round(mae, 6), "mse": round(mse, 6),
                      "rmse": round(rmse, 6), "r2": round(r2, 6),
                      "n": n},
            execution_time_ms=elapsed,
        )

    @staticmethod
    def _parse_numbers(data: Any) -> List[float]:
        import re
        if isinstance(data, list):
            return [float(x) for x in data if _is_numeric(x)]
        if isinstance(data, str):
            numbers = re.findall(r"[-+]?\d*\.?\d+", data)
            return [float(n) for n in numbers]
        return []


def _is_numeric(val: Any) -> bool:
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


class RankingMetricsScorer(BaseScorer):
    """Evaluates ranking quality with NDCG, MRR, and MAP.

    Output is a ranked list of items; expected is the set of relevant items
    or a dict mapping items to relevance scores.
    """

    name = "ranking_metrics"
    description = "Ranking quality: NDCG@K, MRR, MAP"

    def __init__(self, k: int = 10, metric: str = "ndcg"):
        self.k = k
        self.metric = metric.lower()

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", kwargs.get("relevant", ""))

        predictions = self._parse_ranked_list(output)
        relevance = self._parse_relevance(expected)

        if not predictions or not relevance:
            return ScorerResult(name=self.name, score=0.0, reason="No predictions/relevant items", passed=False)

        k = min(self.k, len(predictions))
        metrics: Dict[str, float] = {}
        metrics["ndcg"] = self._ndcg(predictions[:k], relevance)
        metrics["mrr"] = self._mrr(predictions[:k], relevance)
        metrics["map"] = self._map(predictions[:k], relevance)
        metrics["precision_at_k"] = self._precision_at_k(predictions[:k], relevance)
        metrics["recall_at_k"] = self._recall_at_k(predictions[:k], relevance)

        score = metrics.get(self.metric, metrics["ndcg"])
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"NDCG@{k}={metrics['ndcg']:.4f} MRR={metrics['mrr']:.4f} MAP={metrics['map']:.4f}",
            passed=score >= kwargs.get("threshold", 0.3),
            metadata={k_: round(v, 4) for k_, v in metrics.items()},
            execution_time_ms=elapsed,
        )

    def _ndcg(self, ranked: List[str], relevance: Dict[str, float]) -> float:
        dcg = sum(
            (2 ** relevance.get(item, 0) - 1) / math.log2(i + 2)
            for i, item in enumerate(ranked)
        )
        ideal = sorted(relevance.values(), reverse=True)[: len(ranked)]
        idcg = sum((2 ** rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal))
        return dcg / idcg if idcg > 0 else 0.0

    def _mrr(self, ranked: List[str], relevance: Dict[str, float]) -> float:
        for i, item in enumerate(ranked):
            if relevance.get(item, 0) > 0:
                return 1.0 / (i + 1)
        return 0.0

    def _map(self, ranked: List[str], relevance: Dict[str, float]) -> float:
        relevant_count = 0
        precision_sum = 0.0
        for i, item in enumerate(ranked):
            if relevance.get(item, 0) > 0:
                relevant_count += 1
                precision_sum += relevant_count / (i + 1)
        total_relevant = sum(1 for v in relevance.values() if v > 0)
        return precision_sum / total_relevant if total_relevant > 0 else 0.0

    def _precision_at_k(self, ranked: List[str], relevance: Dict[str, float]) -> float:
        relevant = sum(1 for item in ranked if relevance.get(item, 0) > 0)
        return relevant / len(ranked) if ranked else 0.0

    def _recall_at_k(self, ranked: List[str], relevance: Dict[str, float]) -> float:
        total_relevant = sum(1 for v in relevance.values() if v > 0)
        if total_relevant == 0:
            return 0.0
        relevant = sum(1 for item in ranked if relevance.get(item, 0) > 0)
        return relevant / total_relevant

    @staticmethod
    def _parse_ranked_list(data: Any) -> List[str]:
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, str):
            import json
            stripped = data.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    return [str(x) for x in parsed]
                except json.JSONDecodeError:
                    pass
            # Newline or comma separated
            import re
            items = re.split(r"[\n,]", stripped)
            return [s.strip() for s in items if s.strip()]
        return [str(data)]

    @staticmethod
    def _parse_relevance(data: Any) -> Dict[str, float]:
        import json
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
        if isinstance(data, (list, set)):
            return {str(x): 1.0 for x in data}
        if isinstance(data, str):
            stripped = data.strip()
            if stripped.startswith("{"):
                try:
                    parsed = json.loads(stripped)
                    return {str(k): float(v) for k, v in parsed.items()}
                except json.JSONDecodeError:
                    pass
            # Comma-separated items → binary relevance
            items = [s.strip() for s in stripped.split(",") if s.strip()]
            return {item: 1.0 for item in items}
        return {str(data): 1.0}
