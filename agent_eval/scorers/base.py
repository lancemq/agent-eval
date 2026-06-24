"""Base scorer class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ScorerResult:
    """Result from a scorer evaluation."""
    name: str
    score: float
    reason: str = ""
    passed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "reason": self.reason,
            "passed": self.passed,
            "metadata": self.metadata,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseScorer(ABC):
    """Base class for all scorers."""

    name: str = ""
    description: str = ""
    requires_text: bool = False
    requires_context: bool = False
    requires_expected: bool = False

    @abstractmethod
    def score(self, output: str, **kwargs) -> ScorerResult:
        """Score an output, returning a ScorerResult with score (0-1) and reason."""
        pass

    def _build_rubric(self, criteria: str) -> str:
        return f"""You are evaluating an AI output based on the following criteria:

CRITERIA:
{criteria}

Evaluate the output carefully and provide:
1. A score between 0.0 and 1.0
2. A short reason for your score

Score format: SCORE: <number>
Reason format: REASON: <text>"""

    def _call_llm(self, prompt: str, model: str = None) -> str:
        from agent_eval.llm_client import LLMClient

        # Try to load configured eval model (silently falls back to defaults)
        api_key = None
        base_url = None
        try:
            import os
            from agent_eval.web.eval_model import EvalModelConfigStore
            cfg = EvalModelConfigStore(os.getcwd()).load_for_scorer()
            if model is None:
                model = cfg.get("model") or "gpt-4o-mini"
            api_key = cfg.get("api_key") or None
            base_url = cfg.get("base_url") or None
        except Exception:
            if model is None:
                model = "gpt-4o-mini"

        client = LLMClient(model=model, timeout=60.0, max_retries=3, api_key=api_key, base_url=base_url)
        response = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()

    def _parse_score(self, text: str) -> float:
        import re
        patterns = [
            r"SCORE:\s*([\d.]+)",
            r"Score:\s*([\d.]+)",
            r"score:\s*([\d.]+)",
            r"^([\d.]+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                try:
                    val = float(match.group(1))
                    if 0.0 <= val <= 1.0:
                        return val
                except ValueError:
                    continue
        numbers = re.findall(r"\b(0\.\d+|1\.0)\b", text)
        if numbers:
            return float(numbers[-1])
        return 0.5

    def _parse_reason(self, text: str) -> str:
        import re
        match = re.search(r"REASON:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        lines = text.strip().split("\n")
        meaningful = [ln for ln in lines if ln.strip() and not ln.strip().startswith("SCORE:")]
        return meaningful[-1].strip() if meaningful else text[:200]