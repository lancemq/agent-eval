"""Text similarity scorers: BLEU, ROUGE, F1, Edit Distance, Jaccard, Cosine, Semantic.

Most are deterministic (no LLM needed), using standard NLP metrics.
SemanticSimilarity optionally uses sentence-transformers embeddings.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Optional
from agent_eval.scorers.base import BaseScorer, ScorerResult


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def _ngrams(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


class BLEUScorer(BaseScorer):
    """BLEU score for evaluating generated text against references.

    Computes BLEU-N (default N=4) with brevity penalty.
    """

    name = "bleu"
    description = "BLEU-N score for text generation quality"

    def __init__(self, max_n: int = 4, weights: Optional[List[float]] = None):
        self.max_n = max_n
        self.weights = weights or [1.0 / max_n] * max_n

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        references = kwargs.get("expected", kwargs.get("references", ""))
        if not references:
            return ScorerResult(name=self.name, score=0.0, reason="No reference provided", passed=False)

        if isinstance(references, str):
            references = [references]

        candidate = _tokenize(output)
        ref_tokens = [_tokenize(r) for r in references]

        if not candidate:
            return ScorerResult(name=self.name, score=0.0, reason="Empty output", passed=False)

        precisions: List[float] = []
        for n in range(1, self.max_n + 1):
            cand_ngrams = _ngrams(candidate, n)
            max_ref_counts: Counter = Counter()
            for ref in ref_tokens:
                ref_ngrams = _ngrams(ref, n)
                for gram, count in ref_ngrams.items():
                    max_ref_counts[gram] = max(max_ref_counts[gram], count)

            clipped = sum(min(count, max_ref_counts.get(gram, 0)) for gram, count in cand_ngrams.items())
            total = sum(cand_ngrams.values())
            precisions.append(clipped / total if total > 0 else 0.0)

        if min(precisions) == 0:
            bleu = 0.0
        else:
            log_avg = sum(w * math.log(p) for w, p in zip(self.weights, precisions))
            bleu = math.exp(log_avg)

        # Brevity penalty
        ref_lens = [len(r) for r in ref_tokens]
        closest_ref_len = min(ref_lens, key=lambda r: abs(r - len(candidate)))
        bp = 1.0 if len(candidate) > closest_ref_len else math.exp(1 - closest_ref_len / max(len(candidate), 1))
        bleu = bp * bleu

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(bleu, 4),
            reason=f"BLEU-{self.max_n}: {bleu:.4f} (BP={bp:.3f})",
            passed=bleu >= kwargs.get("threshold", 0.3),
            metadata={"bleu": bleu, "brevity_penalty": bp, "precisions": precisions},
            execution_time_ms=elapsed,
        )


class ROUGEScorer(BaseScorer):
    """ROUGE-N and ROUGE-L scores for summarization evaluation."""

    name = "rouge"
    description = "ROUGE-N and ROUGE-L for summarization quality"

    def __init__(self, n: int = 1, use_l: bool = True):
        self.n = n
        self.use_l = use_l

    def _rouge_n(self, candidate: List[str], reference: List[str], n: int) -> float:
        cand_ngrams = _ngrams(candidate, n)
        ref_ngrams = _ngrams(reference, n)
        overlap = sum((cand_ngrams & ref_ngrams).values())
        total_ref = sum(ref_ngrams.values())
        return overlap / total_ref if total_ref > 0 else 0.0

    def _lcs_length(self, a: List[str], b: List[str]) -> int:
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        return dp[m][n]

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        reference = kwargs.get("expected", kwargs.get("reference", ""))
        if not reference:
            return ScorerResult(name=self.name, score=0.0, reason="No reference provided", passed=False)

        candidate = _tokenize(output)
        ref = _tokenize(reference)

        scores: dict = {}
        if self.n > 0:
            scores[f"rouge_{self.n}"] = self._rouge_n(candidate, ref, self.n)

        if self.use_l:
            lcs = self._lcs_length(candidate, ref)
            total = len(candidate) + len(ref)
            if total > 0:
                r_lcs = lcs / max(len(ref), 1)
                p_lcs = lcs / max(len(candidate), 1)
                scores["rouge_l"] = 2 * r_lcs * p_lcs / (r_lcs + p_lcs) if (r_lcs + p_lcs) > 0 else 0.0
            else:
                scores["rouge_l"] = 0.0

        avg = sum(scores.values()) / len(scores) if scores else 0.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(avg, 4),
            reason=f"ROUGE scores: {scores}",
            passed=avg >= kwargs.get("threshold", 0.3),
            metadata=scores,
            execution_time_ms=elapsed,
        )


class F1TokenScorer(BaseScorer):
    """Token-level F1 score between output and expected answer."""

    name = "f1_token"
    description = "Token-level F1 score (precision, recall, F1)"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value", passed=False)

        cand_set = set(_tokenize(output))
        ref_set = set(_tokenize(expected))

        if not cand_set and not ref_set:
            return ScorerResult(name=self.name, score=1.0, reason="Both empty", passed=True)

        tp = len(cand_set & ref_set)
        fp = len(cand_set - ref_set)
        fn = len(ref_set - cand_set)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name, score=round(f1, 4),
            reason=f"P={precision:.3f} R={recall:.3f} F1={f1:.3f}",
            passed=f1 >= kwargs.get("threshold", 0.5),
            metadata={"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn},
            execution_time_ms=elapsed,
        )


class EditDistanceScorer(BaseScorer):
    """Normalized Levenshtein edit distance scorer."""

    name = "edit_distance"
    description = "Normalized Levenshtein edit distance (1 = identical)"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value", passed=False)

        s1, s2 = str(output), str(expected)
        m, n = len(s1), len(s2)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, n + 1):
                temp = dp[j]
                if s1[i - 1] == s2[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(dp[j], dp[j - 1], prev)
                prev = temp

        dist = dp[n]
        max_len = max(m, n, 1)
        score = 1.0 - dist / max_len
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Edit distance: {dist}/{max_len} = {score:.4f}",
            passed=score >= kwargs.get("threshold", 0.7),
            metadata={"distance": dist, "max_length": max_len},
            execution_time_ms=elapsed,
        )


class JaccardScorer(BaseScorer):
    """Jaccard similarity between token sets of output and expected."""

    name = "jaccard"
    description = "Jaccard similarity coefficient for text comparison"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value", passed=False)

        set_a = set(_tokenize(output))
        set_b = set(_tokenize(expected))

        union = set_a | set_b
        intersection = set_a & set_b
        score = len(intersection) / len(union) if union else 1.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Intersection={len(intersection)} Union={len(union)}",
            passed=score >= kwargs.get("threshold", 0.3),
            metadata={"intersection": len(intersection), "union": len(union)},
            execution_time_ms=elapsed,
        )


class CosineSimilarityScorer(BaseScorer):
    """Cosine similarity using TF-IDF vectors (no external dependencies)."""

    name = "cosine_similarity"
    description = "Cosine similarity with TF-IDF vectors"

    def _tfidf_vectors(self, text_a: str, text_b: str):
        tokens_a = _tokenize(text_a)
        tokens_b = _tokenize(text_b)
        all_tokens = set(tokens_a) | set(tokens_b)

        tf_a = Counter(tokens_a)
        tf_b = Counter(tokens_b)

        # IDF (binary since only 2 docs)
        vec_a = {t: tf_a.get(t, 0) for t in all_tokens}
        vec_b = {t: tf_b.get(t, 0) for t in all_tokens}
        return vec_a, vec_b

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value", passed=False)

        vec_a, vec_b = self._tfidf_vectors(str(output), str(expected))
        dot = sum(vec_a[t] * vec_b[t] for t in vec_a)
        norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
        score = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Cosine similarity: {score:.4f}",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"dot_product": dot, "norm_a": norm_a, "norm_b": norm_b},
            execution_time_ms=elapsed,
        )


class SemanticSimilarityScorer(BaseScorer):
    """Semantic similarity using sentence embeddings (optional sentence-transformers).

    Requires `pip install sentence-transformers`. Falls back to
    CosineSimilarityScorer if not available.
    """

    name = "semantic_similarity"
    description = "Semantic similarity via sentence embeddings (sentence-transformers)"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", threshold: float = 0.5):
        self.model_name = model_name
        self.threshold = threshold
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                return None
        return self._model

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", "")
        threshold = kwargs.get("threshold", self.threshold)
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value", passed=False)

        model = self._get_model()
        if model is None:
            # Fallback to cosine similarity
            fallback = CosineSimilarityScorer()
            return fallback.score(output, expected=expected)

        embeddings = model.encode([str(output), str(expected)])
        a, b = embeddings[0], embeddings[1]
        dot = float(a @ b)
        score = dot / (float(math.sqrt(a @ a)) * float(math.sqrt(b @ b)))
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Semantic similarity: {score:.4f}",
            passed=score >= threshold,
            metadata={"model": self.model_name},
            execution_time_ms=elapsed,
        )
