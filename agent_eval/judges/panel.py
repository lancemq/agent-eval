"""Multi-judge panel for cross-validation."""

import statistics
import time
from typing import Any, Dict, List
from agent_eval.judges.base import BaseJudge


class MultiJudgePanel:
    """Panel of judges for cross-validation and robust scoring."""
    
    def __init__(
        self, 
        judges: List[BaseJudge], 
        aggregation: str = "weighted",
        weights: Dict[str, float] = None,
        consistency_threshold: float = 0.3,
    ):
        self.judges = judges
        self.aggregation = aggregation
        self.weights = weights or {j.name: 1.0/len(judges) for j in judges}
        self.consistency_threshold = consistency_threshold
    
    def evaluate(self, task: Dict[str, Any], output: Any) -> Dict[str, Any]:
        """Evaluate with all judges and aggregate results."""
        results = {}
        scores = []
        
        for judge in self.judges:
            try:
                start = time.time()
                score = judge.score(task, output)
                explanation = judge.explain(task, output, score)
                exec_time = int((time.time() - start) * 1000)
                
                results[judge.name] = {
                    "score": score,
                    "explanation": explanation,
                    "execution_time_ms": exec_time,
                }
                scores.append(score)
            except Exception as e:
                results[judge.name] = {
                    "score": 0.0,
                    "explanation": f"ERROR: {e}",
                    "execution_time_ms": 0,
                }
                scores.append(0.0)
        
        # Calculate consistency
        if len(scores) > 1:
            stdev = statistics.stdev(scores)
            consistency = max(0.0, 1.0 - stdev * 2)
        else:
            consistency = 1.0
        
        results["_consistency"] = consistency
        results["_consistency_passed"] = consistency >= (1.0 - self.consistency_threshold)
        
        # Aggregate final score
        final_score = self._aggregate(scores, results)
        results["_final"] = final_score
        results["_scores"] = scores
        results["_mean"] = statistics.mean(scores) if scores else 0.0
        results["_median"] = statistics.median(scores) if scores else 0.0
        results["_stdev"] = statistics.stdev(scores) if len(scores) > 1 else 0.0
        
        return results
    
    def _aggregate(self, scores: List[float], results: Dict) -> float:
        if self.aggregation == "weighted":
            weighted_sum = 0.0
            total_weight = 0.0
            for judge in self.judges:
                weight = self.weights.get(judge.name, 0.0)
                score = results.get(judge.name, {}).get("score", 0.0)
                weighted_sum += score * weight
                total_weight += weight
            return weighted_sum / total_weight if total_weight > 0 else 0.0
        
        elif self.aggregation == "median":
            return statistics.median(scores) if scores else 0.0
        
        elif self.aggregation == "mean":
            return statistics.mean(scores) if scores else 0.0
        
        elif self.aggregation == "unanimous":
            return 1.0 if all(s > 0.5 for s in scores) else 0.0
        
        elif self.aggregation == "majority":
            return 1.0 if sum(1 for s in scores if s > 0.5) > len(scores) / 2 else 0.0
        
        elif self.aggregation == "min":
            return min(scores) if scores else 0.0
        
        elif self.aggregation == "max":
            return max(scores) if scores else 0.0
        
        return statistics.median(scores) if scores else 0.0
    
    def get_judge_details(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": j.name,
                "description": getattr(j, "description", ""),
            }
            for j in self.judges
        ]


class JudgePanelResult:
    """Wrapper for panel evaluation results."""
    
    def __init__(self, results: Dict[str, Any]):
        self.results = results
    
    @property
    def final_score(self) -> float:
        return self.results.get("_final", 0.0)
    
    @property
    def consistency(self) -> float:
        return self.results.get("_consistency", 0.0)
    
    @property
    def judge_scores(self) -> Dict[str, float]:
        return {
            k: v["score"] 
            for k, v in self.results.items() 
            if not k.startswith("_") and isinstance(v, dict)
        }
    
    @property
    def passed(self) -> bool:
        return self.final_score >= 0.5 and self.results.get("_consistency_passed", True)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.results