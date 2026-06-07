"""Relevancy scorers: Answer Relevancy and Contextual Relevancy."""

from agent_eval.scorers.base import BaseScorer, ScorerResult


class AnswerRelevancyScorer(BaseScorer):
    """Measures how relevant the generated answer is to the input query.

    Inspired by DeepEval's AnswerRelevancyMetric. Higher score means the
    answer directly addresses the query without irrelevant information.
    """

    name = "answer_relevancy"
    description = "Measures how relevant the answer is to the input query"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        inp = kwargs.get("input", kwargs.get("task", {}).get("prompt", ""))
        if not inp:
            return ScorerResult(name=self.name, score=0.5, reason="No input provided", passed=True, execution_time_ms=0)

        prompt = f"""You are evaluating the relevancy of an AI-generated answer to the user's query.

USER QUERY:
{inp}

AI ANSWER:
{output}

Evaluate:
1. Does the answer directly address the user's question? (0.0-1.0)
2. Does the answer contain irrelevant or off-topic information? (0.0-1.0, higher = less irrelevant)
3. Is the answer focused and concise relative to the query? (0.0-1.0)

Overall Score: <weighted average, 0.0-1.0>
Reason: <explanation of the score>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason or f"Answer relevancy: {score:.2f}",
            passed=score >= 0.5,
            execution_time_ms=elapsed,
        )


class ContextualRelevancyScorer(BaseScorer):
    """Measures how relevant the retrieved context is to the input query.

    Useful for evaluating RAG retrieval quality. Higher score means the
    retrieved context contains information pertinent to the query.
    """

    name = "contextual_relevancy"
    description = "Measures how relevant the retrieval context is to the input query"
    requires_context = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        context = kwargs.get("context", kwargs.get("retrieval_context", ""))
        inp = kwargs.get("input", kwargs.get("task", {}).get("prompt", ""))
        if not context:
            return ScorerResult(name=self.name, score=0.0, reason="No context provided", passed=False, execution_time_ms=0)
        if not inp:
            return ScorerResult(name=self.name, score=0.5, reason="No input provided", passed=True, execution_time_ms=0)

        if isinstance(context, list):
            context_str = "\n---\n".join(context)
        else:
            context_str = str(context)

        prompt = f"""You are evaluating how relevant a retrieved context is to a user query.

USER QUERY:
{inp}

RETRIEVED CONTEXT:
{context_str[:6000]}

Evaluate:
1. **Signal vs Noise**: What proportion of the context is actually useful for answering the query? (0.0-1.0)
2. **Coverage**: Does the context contain ALL information needed to answer the query? (0.0-1.0)

Overall Score: <weighted average, 0.0-1.0>
Reason: <explanation of relevance>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            execution_time_ms=elapsed,
        )


class ContextualRecallScorer(BaseScorer):
    """Measures whether the retrieved context contains the information needed to answer.

    Inspired by DeepEval's ContextualRecallMetric. Higher score means
    the ground-truth answer can be fully attributed to the context.
    """

    name = "contextual_recall"
    description = "Measures if the context contains the information needed to answer"
    requires_context = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        context = kwargs.get("context", kwargs.get("retrieval_context", ""))
        expected = kwargs.get("expected", kwargs.get("expected_output", ""))
        if not context:
            return ScorerResult(name=self.name, score=0.0, reason="No context provided", passed=False, execution_time_ms=0)

        if isinstance(context, list):
            context_str = "\n".join(context)
        else:
            context_str = str(context)

        reference = expected or output

        prompt = f"""You are evaluating whether a given context contains all the information needed to support the expected answer.

CONTEXT:
{context_str[:6000]}

EXPECTED ANSWER:
{reference}

Task:
1. Break down the expected answer into individual factual statements.
2. For each statement, determine if it is supported by the context.
3. Calculate recall = supported_statements / total_statements

Result:
Total statements: <number>
Supported statements: <number>
Contextual Recall: <score 0.0-1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            execution_time_ms=elapsed,
        )


class ContextualPrecisionScorer(BaseScorer):
    """Measures if relevant documents are ranked higher in the retrieval results.

    Inspired by DeepEval's ContextualPrecisionMetric. Higher score means
    the retrieval system placed more relevant items at the top.
    """

    name = "contextual_precision"
    description = "Measures if relevant documents are ranked higher in context"
    requires_context = True

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        context = kwargs.get("context", kwargs.get("retrieval_context", ""))
        inp = kwargs.get("input", kwargs.get("task", {}).get("prompt", ""))
        if not context:
            return ScorerResult(name=self.name, score=0.0, reason="No context provided", passed=False, execution_time_ms=0)
        if not inp:
            return ScorerResult(name=self.name, score=0.5, reason="No input provided", passed=True, execution_time_ms=0)

        if isinstance(context, list):
            context_items = context
            context_str = "\n---\n".join(f"[Position {i+1}] {c}" for i, c in enumerate(context))
        else:
            context_items = [context]
            context_str = f"[Position 1] {context}"

        if len(context_items) < 2:
            return ScorerResult(
                name=self.name, score=1.0, reason="Only one context item, precision is maximal",
                passed=True, metadata={"items": 1}, execution_time_ms=int((time.time() - start) * 1000),
            )

        prompt = f"""You are evaluating whether a retrieval system ranked relevant documents higher.

USER QUERY:
{inp}

RETRIEVED DOCUMENTS (in ranked order):
{context_str[:8000]}

Task:
1. For each document, determine if it is relevant to the query.
2. Check if relevant documents appear at higher positions (lower number = better).
3. Score precision based on how well the ranking separates relevant from irrelevant.

Result:
Relevant positions: <list of position numbers>
Precision@k analysis: <text>
Contextual Precision: <score 0.0-1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            metadata={"num_documents": len(context_items)},
            execution_time_ms=elapsed,
        )