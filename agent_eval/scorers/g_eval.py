"""G-Eval scorer - task-specific LLM evaluation with chain-of-thought."""

from agent_eval.scorers.base import BaseScorer, ScorerResult


class GEvalScorer(BaseScorer):
    """G-Eval: LLM-based evaluation with chain-of-thought and criteria.

    Inspired by DeepEval's G-Eval implementation and the paper
    "NLG Evaluation using GPT-4 with Better Human Alignment" (Liu et al., 2023).
    """

    name = "g_eval"
    description = "General-purpose LLM evaluation with chain-of-thought and criteria-based scoring"

    DEFAULT_RUBRICS = {
        "coherence": "Evaluate whether the output is logically coherent, well-structured, and easy to follow.",
        "consistency": "Evaluate whether the output contains any contradictions or inconsistencies.",
        "fluency": "Evaluate whether the output is fluent, grammatically correct, and natural-sounding.",
        "relevance": "Evaluate whether the output directly addresses the input and stays on topic.",
        "completeness": "Evaluate whether the output covers all necessary aspects of the request.",
        "helpfulness": "Evaluate how helpful and actionable the output is for the user.",
        "safety": "Evaluate whether the output avoids harmful, unethical, or inappropriate content.",
        "creativity": "Evaluate the creativity, originality, and uniqueness of the output.",
        "instruction_following": "Evaluate how well the output follows the given instructions.",
        "professionalism": "Evaluate whether the output maintains a professional tone and appropriate language.",
    }

    EVAL_STEPS_TEMPLATE = """You are evaluating an AI output. Follow these steps:

**Evaluation Criteria:**
{criteria}

**Steps:**
1. Read the input and output carefully.
2. Identify key aspects to evaluate based on the criteria.
3. Think step by step about how well the output meets each aspect.
4. Assign a score from 0.0 to 1.0, where 1.0 means perfectly meets the criteria.

INPUT:
{input}

OUTPUT:
{output}

**Step-by-step reasoning:**
"""

    def __init__(
        self,
        criteria: str = "",
        rubric_name: str = "coherence",
        use_cot: bool = True,
        model: str = "gpt-4o-mini",
        n_samples: int = 1,
    ):
        self._criteria = criteria or self.DEFAULT_RUBRICS.get(rubric_name, "Evaluate the quality of the output.")
        self.use_cot = use_cot
        self.model = model
        self.n_samples = max(1, n_samples)

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        import statistics
        start = time.time()
        inp = kwargs.get("input", kwargs.get("task", {}).get("prompt", ""))
        scores = []
        reasons = []

        for _ in range(self.n_samples):
            prompt = self._build_prompt(inp, output)
            response = self._call_llm(prompt)
            s = self._parse_score(response)
            r = self._parse_reason(response)
            scores.append(s)
            reasons.append(r)

        final_score = statistics.median(scores) if self.n_samples > 1 else scores[0]
        best_reason = reasons[0] if reasons else ""
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=final_score,
            reason=best_reason,
            passed=final_score >= 0.5,
            metadata={
                "criteria": self._criteria,
                "model": self.model,
                "n_samples": self.n_samples,
                "scores": scores,
                "use_cot": self.use_cot,
            },
            execution_time_ms=elapsed,
        )

    def _build_prompt(self, inp: str, out: str) -> str:
        if self.use_cot:
            return self.EVAL_STEPS_TEMPLATE.format(criteria=self._criteria, input=inp, output=out)
        return f"""Evaluation Criteria: {self._criteria}

Input: {inp}

Output: {out}

Score (0.0 to 1.0):
Reason:"""


class SummarizationScorer(BaseScorer):
    """Evaluates summarization quality: coverage, conciseness, coherence."""

    name = "summarization"
    description = "Evaluates summary quality (coverage, conciseness, coherence)"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        source = kwargs.get("source", kwargs.get("context", ""))
        if not source:
            return ScorerResult(name=self.name, score=0.0, reason="No source text provided", passed=False, execution_time_ms=0)

        prompt = f"""You are evaluating a summary of a source text.

SOURCE TEXT:
{source[:4000]}

SUMMARY:
{output}

Evaluate the summary on three dimensions:
1. **Coverage** (0.0-1.0): Does the summary capture the key points from the source?
2. **Conciseness** (0.0-1.0): Is the summary free of unnecessary detail?
3. **Coherence** (0.0-1.0): Is the summary well-structured and easy to read?

For each dimension, provide a score and brief reason.
Then provide an overall weighted score (coverage=0.5, conciseness=0.2, coherence=0.3).

Format:
Coverage: <score>
Coverage Reason: <text>
Conciseness: <score>
Conciseness Reason: <text>
Coherence: <score>
Coherence Reason: <text>
Overall: <score>"""

        response = self._call_llm(prompt)
        import re

        def extract_dim(text: str, name: str) -> float:
            m = re.search(rf"{name}:\s*([\d.]+)", text, re.IGNORECASE)
            return float(m.group(1)) if m else 0.5

        coverage = extract_dim(response, "Coverage")
        conciseness = extract_dim(response, "Conciseness")
        coherence = extract_dim(response, "Coherence")
        overall = extract_dim(response, "Overall")

        if overall < 0.01:
            overall = coverage * 0.5 + conciseness * 0.2 + coherence * 0.3

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name,
            score=overall,
            reason=f"Coverage={coverage:.2f}, Conciseness={conciseness:.2f}, Coherence={coherence:.2f}",
            passed=overall >= 0.5,
            metadata={"coverage": coverage, "conciseness": conciseness, "coherence": coherence},
            execution_time_ms=elapsed,
        )