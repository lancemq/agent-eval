"""Faithfulness, Hallucination, and Answer Correctness scorers."""

from agent_eval.scorers.base import BaseScorer, ScorerResult


class FaithfulnessScorer(BaseScorer):
    """Measures whether the output is faithful to the provided context (no contradictions).

    Inspired by DeepEval's FaithfulnessMetric. Checks if all claims in the
    output can be attributed to the given context.
    """

    name = "faithfulness"
    description = "Measures if the output is faithful to the provided context (no contradictions)"
    requires_context = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        context = kwargs.get("context", kwargs.get("retrieval_context", ""))
        if not context or not isinstance(context, (str, list)):
            return ScorerResult(name=self.name, score=0.0, reason="No context provided", passed=False, execution_time_ms=0)

        if isinstance(context, list):
            context = "\n".join(context)

        prompt = f"""You are evaluating whether an AI output is faithful to the provided context.
A faithful output only contains claims that are supported by the context.
Any claim in the output that is NOT supported by (or contradicts) the context is a hallucination.

CONTEXT:
{context[:6000]}

OUTPUT:
{output}

Task:
1. Extract all factual claims from the output.
2. For each claim, check if it is supported by the context.
3. Count unsupported claims.
4. Calculate faithfulness = 1 - (unsupported_claims / total_claims).

Respond with:
Total claims in output: <number>
Unsupported claims: <number>
Faithfulness score: <number between 0.0 and 1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        import re
        total_m = re.search(r"Total claims.*?:\s*(\d+)", response, re.IGNORECASE)
        unsup_m = re.search(r"Unsupported claims.*?:\s*(\d+)", response, re.IGNORECASE)
        metadata = {}
        if total_m:
            metadata["total_claims"] = int(total_m.group(1))
        if unsup_m:
            metadata["unsupported_claims"] = int(unsup_m.group(1))

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.7,
            metadata=metadata,
            execution_time_ms=elapsed,
        )


class HallucinationScorer(BaseScorer):
    """Detects hallucinations in model output relative to context.

    Higher score = less hallucination (more grounded in context).
    """

    name = "hallucination"
    description = "Detects unsupported claims (hallucinations) in output relative to context"
    requires_context = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        result = FaithfulnessScorer().score(output, **kwargs)
        result.name = self.name
        return result


class AnswerCorrectnessScorer(BaseScorer):
    """Measures correctness of the answer against a ground-truth expected output.

    Evaluates both factual accuracy and semantic alignment.
    """

    name = "answer_correctness"
    description = "Measures answer correctness against expected ground truth"
    requires_expected = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", kwargs.get("expected_output", ""))
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected output provided", passed=False, execution_time_ms=0)

        prompt = f"""You are evaluating the correctness of an AI output compared to the expected answer.

Expected answer:
{expected}

Actual output:
{output}

Evaluate:
1. **Factual Accuracy**: Does the output contain correct factual information? (weight: 0.6)
2. **Semantic Alignment**: Does the output convey the same meaning as the expected answer? (weight: 0.4)

Provide a final score from 0.0 to 1.0, where 1.0 means perfectly correct.

Factual Accuracy: <score>
Semantic Alignment: <score>
Overall Score: <score>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        import re
        fa_m = re.search(r"Factual Accuracy.*?:\s*([\d.]+)", response, re.IGNORECASE)
        sa_m = re.search(r"Semantic Alignment.*?:\s*([\d.]+)", response, re.IGNORECASE)
        metadata = {}
        if fa_m:
            metadata["factual_accuracy"] = float(fa_m.group(1))
        if sa_m:
            metadata["semantic_alignment"] = float(sa_m.group(1))

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            metadata=metadata,
            execution_time_ms=elapsed,
        )