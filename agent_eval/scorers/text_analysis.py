"""Text analysis scorers: readability, diversity, sentiment, grammar, tone, coherence, fluency."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List
from agent_eval.scorers.base import BaseScorer, ScorerResult


def _sentences(text: str) -> List[str]:
    sents = re.split(r"[.!?]+", text)
    return [s.strip() for s in sents if s.strip()]


def _words(text: str) -> List[str]:
    return re.findall(r"\b[a-zA-Z]+\b", text.lower())


def _syllables(word: str) -> int:
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e"):
        count = max(1, count - 1)
    return max(1, count)


class ReadabilityScorer(BaseScorer):
    """Flesch Reading Ease and Flesch-Kincaid Grade Level.

    Higher reading ease = easier to read (score scaled to 0-1).
    """

    name = "readability"
    description = "Flesch Reading Ease and Flesch-Kincaid Grade Level"

    def __init__(self, target_grade: float = 8.0):
        self.target_grade = target_grade

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output)
        sents = _sentences(text)
        words = _words(text)

        if not sents or not words:
            return ScorerResult(name=self.name, score=0.0, reason="Empty text", passed=False)

        total_syl = sum(_syllables(w) for w in words)
        words_per_sent = len(words) / len(sents)
        syl_per_word = total_syl / len(words)

        reading_ease = 206.835 - 1.015 * words_per_sent - 84.6 * syl_per_word
        grade_level = 0.39 * words_per_sent + 11.8 * syl_per_word - 15.59

        # Score: closer to target grade = higher score
        grade_diff = abs(grade_level - self.target_grade)
        score = max(0.0, 1.0 - grade_diff / 12.0)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Reading Ease: {reading_ease:.1f}, Grade Level: {grade_level:.1f} (target: {self.target_grade})",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"reading_ease": round(reading_ease, 1), "grade_level": round(grade_level, 1),
                      "words_per_sentence": round(words_per_sent, 1), "syllables_per_word": round(syl_per_word, 2)},
            execution_time_ms=elapsed,
        )


class LexicalDiversityScorer(BaseScorer):
    """Measures lexical diversity (type-token ratio and unique token ratio).

    Higher diversity generally indicates richer vocabulary.
    """

    name = "lexical_diversity"
    description = "Lexical diversity (type-token ratio, unique token ratio)"

    def __init__(self, min_ttr: float = 0.3, max_ttr: float = 0.8):
        self.min_ttr = min_ttr
        self.max_ttr = max_ttr

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        words = _words(str(output))
        if not words:
            return ScorerResult(name=self.name, score=0.0, reason="Empty text", passed=False)

        unique = set(words)
        ttr = len(unique) / len(words)
        # Root TTR (corrected for text length)
        rttr = len(unique) / math.sqrt(len(words)) if words else 0

        # Score: within [min, max] range = 1.0
        if self.min_ttr <= ttr <= self.max_ttr:
            score = 1.0
        elif ttr < self.min_ttr:
            score = ttr / self.min_ttr
        else:
            score = max(0.0, 1.0 - (ttr - self.max_ttr) * 2)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"TTR={ttr:.3f} ({len(unique)} unique / {len(words)} total)",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"ttr": round(ttr, 4), "root_ttr": round(rttr, 4),
                      "unique_words": len(unique), "total_words": len(words)},
            execution_time_ms=elapsed,
        )


class SentimentScorer(BaseScorer):
    """Rule-based sentiment analysis (lexicon approach, no LLM needed).

    Scores: 0.0 = very negative, 0.5 = neutral, 1.0 = very positive.
    """

    name = "sentiment"
    description = "Rule-based sentiment analysis (positive/negative/neutral)"

    POSITIVE_WORDS = {
        "good", "great", "excellent", "amazing", "wonderful", "fantastic", "awesome",
        "perfect", "love", "like", "best", "happy", "glad", "pleased", "satisfied",
        "helpful", "useful", "beneficial", "positive", "correct", "right", "success",
        "win", "benefit", "advantage", "improve", "better", "nice", "beautiful",
        "brilliant", "outstanding", "superb", "delightful", "thank", "appreciate",
    }
    NEGATIVE_WORDS = {
        "bad", "terrible", "awful", "horrible", "worst", "hate", "dislike", "poor",
        "wrong", "incorrect", "error", "fail", "failure", "broken", "useless",
        "harmful", "negative", "disappointing", "disappointed", "sad", "angry",
        "frustrated", "confused", "lost", "stuck", "problem", "issue", "bug",
        "crash", "slow", "difficult", "hard", "impossible", "never", "cannot",
        "stop", "deny", "reject", "refuse", "complaint", "concern", "worry",
    }
    NEGATION_WORDS = {"not", "no", "never", "n't", "hardly", "barely"}

    def __init__(self, expected_polarity: str = ""):
        self.expected_polarity = expected_polarity.lower()

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        words = _words(str(output))
        if not words:
            return ScorerResult(name=self.name, score=0.5, reason="Empty text (neutral)", passed=True)

        pos_count = 0
        neg_count = 0
        for i, w in enumerate(words):
            negated = i > 0 and words[i - 1] in self.NEGATION_WORDS
            if w in self.POSITIVE_WORDS:
                pos_count += 1 if not negated else 0
                neg_count += 1 if negated else 0
            elif w in self.NEGATIVE_WORDS:
                neg_count += 1 if not negated else 0
                pos_count += 1 if negated else 0

        total = pos_count + neg_count
        if total == 0:
            sentiment = 0.5
            polarity = "neutral"
        else:
            sentiment = pos_count / total
            polarity = "positive" if sentiment > 0.6 else "negative" if sentiment < 0.4 else "neutral"

        # If expected polarity specified, score by match
        if self.expected_polarity:
            score = 1.0 if polarity == self.expected_polarity else 0.0
            reason = f"Polarity: {polarity} (expected: {self.expected_polarity})"
        else:
            score = sentiment
            reason = f"Sentiment: {sentiment:.3f} ({polarity}), pos={pos_count} neg={neg_count}"

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=reason,
            passed=score >= kwargs.get("threshold", 0.4),
            metadata={"sentiment": round(sentiment, 4), "polarity": polarity,
                      "positive_count": pos_count, "negative_count": neg_count},
            execution_time_ms=elapsed,
        )


class GrammarCheckScorer(BaseScorer):
    """Basic grammar checking using rule-based heuristics.

    Detects: double words, missing capitalization, spacing issues,
    repeated punctuation, sentence fragments.
    """

    name = "grammar_check"
    description = "Rule-based grammar checking (double words, capitalization, spacing)"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output)
        issues: List[str] = []

        # Double words: "the the", "is is"
        doubles = re.findall(r"\b(\w+)\s+\1\b", text, re.IGNORECASE)
        if doubles:
            issues.append(f"double words: {doubles[:3]}")

        # Missing sentence-start capitalization
        sents = re.split(r"[.!?]+\s+", text)
        for s in sents:
            s = s.strip()
            if s and s[0].isalpha() and not s[0].isupper():
                issues.append(f"uncapitalized sentence start: '{s[:20]}...'")
                break

        # Multiple spaces between words
        if re.search(r"\S\s{2,}\S", text):
            issues.append("multiple spaces between words")

        # Repeated punctuation
        if re.search(r"[.!?,;]{2,}", text):
            issues.append("repeated punctuation")

        # Space before punctuation
        if re.search(r"\s+[.!?,;](?!\w)", text):
            issues.append("space before punctuation")

        # Very short sentences (potential fragments)
        short_sents = [s for s in _sentences(text) if 0 < len(s.split()) <= 2]
        if len(short_sents) > 2:
            issues.append(f"sentence fragments: {len(short_sents)}")

        score = max(0.0, 1.0 - len(issues) * 0.15)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(issues) if issues else 'No grammar issues detected'}",
            passed=score >= kwargs.get("threshold", 0.7),
            metadata={"issues": issues, "num_issues": len(issues)},
            execution_time_ms=elapsed,
        )


class ToneAnalyzerScorer(BaseScorer):
    """Analyzes text tone/formality level.

    Determines: formal, informal, technical, casual, aggressive.
    Uses lexical heuristics (no LLM needed).
    """

    name = "tone_analysis"
    description = "Text tone/formality analysis (formal, informal, technical, etc.)"

    FORMAL_MARKERS = {"furthermore", "however", "therefore", "thus", "hence", "moreover",
                      "consequently", "subsequently", "nevertheless", "accordingly", "thereby"}
    INFORMAL_MARKERS = {"yeah", "ok", "okay", "cool", "awesome", "gonna", "wanna",
                        "kinda", "nah", "lol", "btw", "tbh", "imo"}
    TECHNICAL_MARKERS = {"parameter", "function", "variable", "algorithm", "implementation",
                         "configuration", "optimization", "asynchronous", "concurrency", "polymorphism"}
    AGGRESSIVE_MARKERS = {"stupid", "idiot", "shut up", "obviously", "duh", "moron", "ridiculous"}

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        words = _words(str(output))
        word_set = set(words)
        text_lower = str(output).lower()

        scores = {
            "formal": len(word_set & self.FORMAL_MARKERS),
            "informal": len(word_set & self.INFORMAL_MARKERS),
            "technical": len(word_set & self.TECHNICAL_MARKERS),
            "aggressive": sum(1 for m in self.AGGRESSIVE_MARKERS if m in text_lower),
        }

        dominant = max(scores, key=scores.get) if any(scores.values()) else "neutral"
        total_markers = sum(scores.values())
        confidence = min(1.0, total_markers / 5.0) if total_markers > 0 else 0.5

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(confidence, 4),
            reason=f"Dominant tone: {dominant} (confidence: {confidence:.0%})",
            passed=True,
            metadata={"dominant_tone": dominant, "confidence": confidence, "tone_scores": scores},
            execution_time_ms=elapsed,
        )


class CoherenceScorer(BaseScorer):
    """Text coherence via adjacent sentence similarity.

    Measures how well each sentence connects to the next using
    shared vocabulary overlap.
    """

    name = "coherence"
    description = "Text coherence via adjacent sentence overlap"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        sents = _sentences(str(output))

        if len(sents) < 2:
            return ScorerResult(
                name=self.name, score=0.5,
                reason="Not enough sentences for coherence analysis",
                passed=True, execution_time_ms=0,
            )

        overlaps: List[float] = []
        for i in range(len(sents) - 1):
            words_a = set(_words(sents[i]))
            words_b = set(_words(sents[i + 1]))
            if words_a and words_b:
                overlap = len(words_a & words_b) / len(words_a | words_b)
                overlaps.append(overlap)

        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
        # Scale: 0.1-0.4 typical range, normalize to 0-1
        score = min(1.0, avg_overlap / 0.3)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Avg sentence overlap: {avg_overlap:.3f} across {len(overlaps)} pairs",
            passed=score >= kwargs.get("threshold", 0.4),
            metadata={"avg_overlap": round(avg_overlap, 4), "sentence_pairs": len(overlaps),
                      "overlaps": [round(o, 3) for o in overlaps]},
            execution_time_ms=elapsed,
        )


class FluencyScorer(BaseScorer):
    """Text fluency via length-normalized n-gram repetition penalty.

    Penalizes repetitive patterns and rewards varied sentence structures.
    """

    name = "fluency"
    description = "Text fluency via n-gram repetition and sentence variety"

    def __init__(self, max_ngram_repeat: float = 0.3):
        self.max_ngram_repeat = max_ngram_repeat

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        words = _words(str(output))
        sents = _sentences(str(output))

        if len(words) < 10:
            return ScorerResult(name=self.name, score=0.5, reason="Text too short for fluency", passed=True)

        # 1. N-gram repetition penalty (3-grams)
        trigrams = Counter(tuple(words[i:i+3]) for i in range(len(words) - 2))
        total_trigrams = sum(trigrams.values())
        repeated = sum(c - 1 for c in trigrams.values() if c > 1)
        repeat_ratio = repeated / total_trigrams if total_trigrams > 0 else 0
        repeat_score = max(0.0, 1.0 - repeat_ratio / self.max_ngram_repeat)

        # 2. Sentence length variety (coefficient of variation)
        sent_lens = [len(_words(s)) for s in sents if s.strip()]
        if len(sent_lens) > 1:
            mean_len = sum(sent_lens) / len(sent_lens)
            std_len = (sum((sl - mean_len) ** 2 for sl in sent_lens) / len(sent_lens)) ** 0.5
            cv = std_len / mean_len if mean_len > 0 else 0
            variety_score = min(1.0, cv * 3)  # Higher CV = more variety = better
        else:
            variety_score = 0.5

        # 3. Average sentence length (not too short, not too long)
        avg_len = sum(sent_lens) / len(sent_lens) if sent_lens else 0
        if 10 <= avg_len <= 25:
            length_score = 1.0
        elif avg_len < 10:
            length_score = avg_len / 10
        else:
            length_score = max(0.0, 1.0 - (avg_len - 25) / 50)

        score = (repeat_score * 0.4 + variety_score * 0.3 + length_score * 0.3)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Repeat={repeat_score:.2f} Variety={variety_score:.2f} Length={length_score:.2f}",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"repeat_score": round(repeat_score, 4), "variety_score": round(variety_score, 4),
                      "length_score": round(length_score, 4), "repeat_ratio": round(repeat_ratio, 4),
                      "avg_sentence_length": round(avg_len, 1)},
            execution_time_ms=elapsed,
        )
