"""LLM-based judges."""

import json
import statistics
import time
from typing import Any, Dict, List, Optional
from agent_eval.judges.base import BaseJudge, JudgeResult, LLMJudgeConfig
from agent_eval.llm_client import LLMClient


class LLMJudge(BaseJudge):
    """LLM-based judge with self-consistency and chain-of-thought."""
    
    def __init__(self, config: LLMJudgeConfig):
        self.config = config
        self.name = config.rubric.split("\n")[0][:50] if config.rubric else "llm_judge"
        self.client = LLMClient(
            model=config.model,
            timeout=getattr(config, "timeout", 60.0),
            max_retries=getattr(config, "max_retries", 3),
        )
    
    def score(self, task: Dict[str, Any], output: Any) -> float:
        scores = []
        for _ in range(self.config.n_samples):
            prompt = self._build_prompt(task, output)
            response = self._call_llm(prompt)
            score = self._parse_score(response)
            if score is not None:
                scores.append(score)
        
        if not scores:
            return 0.0
        
        return statistics.median(scores)
    
    def explain(self, task: Dict[str, Any], output: Any, score: float) -> str:
        prompt = self._build_prompt(task, output, include_explanation=True)
        response = self._call_llm(prompt)
        return response
    
    def judge(self, **kwargs) -> JudgeResult:
        start = time.time()
        
        scores = []
        explanations = []
        
        for _ in range(self.config.n_samples):
            prompt = self._build_prompt(
                kwargs.get("task", {}), 
                kwargs.get("output", {}),
                include_explanation=True
            )
            response = self._call_llm(prompt)
            score = self._parse_score(response)
            if score is not None:
                scores.append(score)
                explanations.append(response)
        
        final_score = statistics.median(scores) if scores else 0.0
        explanation = explanations[0] if explanations else ""
        
        exec_time = int((time.time() - start) * 1000)
        
        return JudgeResult(
            score=final_score,
            raw_score={"scores": scores, "median": final_score},
            details={"explanations": explanations},
            passed=final_score >= 0.5,
            execution_time_ms=exec_time,
            explanation=explanation
        )
    
    def _build_prompt(self, task: Dict, output: Any, include_explanation: bool = False) -> str:
        parts = []
        
        if self.config.rubric:
            parts.append(f"RUBRIC:\n{self.config.rubric}\n")
        
        if self.config.few_shot_examples:
            parts.append("EXAMPLES:")
            for i, ex in enumerate(self.config.few_shot_examples):
                parts.append(f"\nExample {i+1}:")
                parts.append(f"Task: {json.dumps(ex.get('task', {}))}")
                parts.append(f"Output: {json.dumps(ex.get('output', {}))}")
                parts.append(f"Score: {ex.get('score', 0)}")
                if ex.get('explanation'):
                    parts.append(f"Explanation: {ex['explanation']}")
            parts.append("")
        
        parts.append("TASK:")
        parts.append(json.dumps(task, ensure_ascii=False))
        parts.append("")
        parts.append("OUTPUT:")
        parts.append(json.dumps(output, ensure_ascii=False))
        parts.append("")
        
        if self.config.use_cot:
            parts.append("Let's think step by step.")
        
        if include_explanation:
            parts.append("Provide your reasoning and then give a final score (0-1).")
        else:
            parts.append("Score (0-1):")
        
        return "\n".join(parts)
    
    def _call_llm(self, prompt: str) -> str:
        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content.strip()
    
    def _parse_score(self, response: str) -> Optional[float]:
        import re
        
        patterns = [
            r"Score:\s*([\d.]+)",
            r"Final Score:\s*([\d.]+)",
            r"Score \(0-1\):\s*([\d.]+)",
            r"^([\d.]+)$",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
            if match:
                try:
                    score = float(match.group(1))
                    if 0 <= score <= 1:
                        return score
                except ValueError:
                    continue
        
        numbers = re.findall(r"\b(0\.\d+|1\.0|0|1)\b", response)
        if numbers:
            try:
                score = float(numbers[-1])
                if 0 <= score <= 1:
                    return score
            except ValueError:
                pass
        
        return None


class EnsembleJudge(BaseJudge):
    """Ensemble of multiple judges with voting."""

    def __init__(self, judges: List[BaseJudge], weights: List[float] = None):
        self.judges = judges
        self.weights = weights or [1.0 / len(judges)] * len(judges)
        self.name = "ensemble"

    def score(self, task: Dict[str, Any], output: Any) -> float:
        weighted_sum = 0.0
        total_weight = 0.0
        for judge, weight in zip(self.judges, self.weights):
            try:
                s = judge.score(task, output)
                weighted_sum += s * weight
                total_weight += weight
            except Exception:
                continue
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def explain(self, task: Dict[str, Any], output: Any, score: float) -> str:
        explanations = []
        for judge in self.judges:
            try:
                s = judge.score(task, output)
                e = judge.explain(task, output, s)
                explanations.append(f"{judge.name}: {s:.2f} - {e}")
            except Exception as e:
                explanations.append(f"{judge.name}: ERROR - {e}")
        return "\n".join(explanations)