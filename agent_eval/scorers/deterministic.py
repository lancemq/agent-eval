"""Deterministic scorers: regex, JSON, length, keyword, exact match, and more."""

import json
import re
from typing import List, Optional, Pattern
from agent_eval.scorers.base import BaseScorer, ScorerResult


class ExactMatchScorer(BaseScorer):
    """Exact string or numeric match between output and expected value."""

    name = "exact_match"
    description = "Exact string/numeric match between output and expected"

    def __init__(self, case_sensitive: bool = True, strip: bool = True):
        self.case_sensitive = case_sensitive
        self.strip = strip

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", kwargs.get("expected_output", ""))
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value provided", passed=False, execution_time_ms=0)

        a = output if isinstance(output, str) else str(output)
        b = expected if isinstance(expected, str) else str(expected)
        if self.strip:
            a, b = a.strip(), b.strip()
        if not self.case_sensitive:
            a, b = a.lower(), b.lower()

        passed = a == b
        score = 1.0 if passed else 0.0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"Exact match: {'PASS' if passed else 'FAIL'}",
            passed=passed,
            metadata={"expected": expected, "got": output},
            execution_time_ms=elapsed,
        )


class NumericMatchScorer(BaseScorer):
    """Numeric comparison with tolerance."""

    name = "numeric_match"
    description = "Numeric comparison with configurable tolerance"

    def __init__(self, tolerance: float = 1e-6):
        self.tolerance = tolerance

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        expected = kwargs.get("expected", kwargs.get("expected_output", ""))
        if not expected:
            return ScorerResult(name=self.name, score=0.0, reason="No expected value provided", passed=False, execution_time_ms=0)

        try:
            out_val = float(re.search(r"[-+]?\d*\.?\d+", str(output)).group())
            exp_val = float(re.search(r"[-+]?\d*\.?\d+", str(expected)).group())
        except (ValueError, AttributeError, TypeError):
            return ScorerResult(name=self.name, score=0.0, reason="Could not parse numbers", passed=False, execution_time_ms=0)

        diff = abs(out_val - exp_val)
        if diff <= self.tolerance:
            score = 1.0
        else:
            score = max(0.0, 1.0 - diff / max(abs(exp_val), 1.0) * 2)
        passed = diff <= self.tolerance
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"Expected {exp_val}, got {out_val}, diff={diff:.2e}",
            passed=passed,
            metadata={"expected": exp_val, "got": out_val, "diff": diff},
            execution_time_ms=elapsed,
        )


class RegexScorer(BaseScorer):
    """Score based on regex pattern matching."""

    name = "regex_match"
    description = "Regex pattern matching scorer"

    def __init__(self, pattern: str = "", flags: int = 0, required: bool = True):
        self.pattern_str = pattern
        self.flags = flags
        self.compiled: Optional[Pattern] = None
        self.required = required
        if pattern:
            self.compiled = re.compile(pattern, flags)

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        pattern = kwargs.get("pattern", self.pattern_str)
        if not pattern:
            return ScorerResult(name=self.name, score=0.5, reason="No pattern provided", passed=True, execution_time_ms=0)

        try:
            compiled = self.compiled if pattern == self.pattern_str else re.compile(pattern)
        except re.error as e:
            return ScorerResult(name=self.name, score=0.0, reason=f"Invalid regex: {e}", passed=False, execution_time_ms=0)

        match = compiled.search(str(output))
        found = match is not None
        score = 1.0 if found == self.required else 0.0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"Pattern {'found' if found else 'not found'} (required={self.required})",
            passed=bool(score),
            metadata={"pattern": pattern, "matched": match.group() if match else None},
            execution_time_ms=elapsed,
        )


class JSONScorer(BaseScorer):
    """Validates JSON structure and optionally checks against a schema."""

    name = "json_valid"
    description = "JSON structure validation scorer"

    def __init__(self, required_keys: Optional[List[str]] = None, validate_schema: bool = False):
        self.required_keys = required_keys or []

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()

        text = output.strip()
        json_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        try:
            data = json.loads(text)
            valid = True
        except json.JSONDecodeError as e:
            elapsed = int((time.time() - start) * 1000)
            return ScorerResult(
                name=self.name, score=0.0, reason=f"Invalid JSON: {e}",
                passed=False, metadata={"error": str(e)}, execution_time_ms=elapsed,
            )

        missing_keys = []
        if self.required_keys:
            if isinstance(data, dict):
                missing_keys = [k for k in self.required_keys if k not in data]
            else:
                missing_keys = self.required_keys

        score = 1.0 if valid and not missing_keys else 0.5 if valid else 0.0
        reason_parts = []
        if valid:
            reason_parts.append("Valid JSON")
        if missing_keys:
            reason_parts.append(f"Missing keys: {missing_keys}")
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason="; ".join(reason_parts) or "Valid JSON",
            passed=valid and not missing_keys,
            metadata={"valid": valid, "missing_keys": missing_keys, "type": type(data).__name__},
            execution_time_ms=elapsed,
        )


class KeywordScorer(BaseScorer):
    """Scores based on presence/absence of keywords."""

    name = "keyword"
    description = "Keyword presence/absence scoring"

    def __init__(self, required_keywords: Optional[List[str]] = None, forbidden_keywords: Optional[List[str]] = None, case_sensitive: bool = False):
        self.required = [k.lower() for k in (required_keywords or [])]
        self.forbidden = [k.lower() for k in (forbidden_keywords or [])]
        self.case_sensitive = case_sensitive

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()

        text = kwargs.get("text", output)
        if not self.case_sensitive:
            text = text.lower()

        found = [k for k in self.required if k in text]
        missing = [k for k in self.required if k not in text]
        present_forbidden = [k for k in self.forbidden if k in text]

        if self.required and self.forbidden:
            score = 1.0 if len(missing) == 0 and len(present_forbidden) == 0 else 0.0
        elif self.required:
            score = len(found) / len(self.required)
        elif self.forbidden:
            score = 0.0 if present_forbidden else 1.0
        else:
            score = 1.0

        passed = score >= 0.5
        reasons = []
        if missing:
            reasons.append(f"Missing: {missing}")
        if present_forbidden:
            reasons.append(f"Forbidden found: {present_forbidden}")
        if not reasons:
            reasons.append("All keyword checks passed")
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=min(score, 1.0),
            reason="; ".join(reasons),
            passed=passed,
            metadata={"found": found, "missing": missing, "forbidden_found": present_forbidden},
            execution_time_ms=elapsed,
        )


class LengthScorer(BaseScorer):
    """Scores based on output length constraints."""

    name = "length"
    description = "Length-based scoring with min/max constraints"

    def __init__(self, min_chars: int = 0, max_chars: int = 0, min_words: int = 0, max_words: int = 0):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.min_words = min_words
        self.max_words = max_words

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()

        text = str(output)
        n_chars = len(text)
        n_words = len(text.split())

        violations = []
        if self.min_chars > 0 and n_chars < self.min_chars:
            violations.append(f"chars({n_chars}) < min({self.min_chars})")
        if self.max_chars > 0 and n_chars > self.max_chars:
            violations.append(f"chars({n_chars}) > max({self.max_chars})")
        if self.min_words > 0 and n_words < self.min_words:
            violations.append(f"words({n_words}) < min({self.min_words})")
        if self.max_words > 0 and n_words > self.max_words:
            violations.append(f"words({n_words}) > max({self.max_words})")

        score = 0.0 if violations else 1.0
        passed = len(violations) == 0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason="; ".join(violations) if violations else f"Length OK ({n_chars} chars, {n_words} words)",
            passed=passed,
            metadata={"chars": n_chars, "words": n_words, "violations": violations},
            execution_time_ms=elapsed,
        )


class ContainsAnyScorer(BaseScorer):
    """Checks if output contains ANY of the given strings/substrings."""

    name = "contains_any"
    description = "Checks if output contains any of the given strings"

    def __init__(self, options: List[str] = None, case_sensitive: bool = False):
        self.options = options or []
        self.case_sensitive = case_sensitive

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        options = kwargs.get("options", self.options)
        text = str(output)
        if not self.case_sensitive:
            text = text.lower()
            options = [o.lower() for o in options]

        found = [o for o in options if o in text]
        score = 1.0 if found else 0.0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"Found: {found}" if found else "None of the options found",
            passed=bool(found),
            metadata={"found": found, "options": options},
            execution_time_ms=elapsed,
        )


class ContainsAllScorer(BaseScorer):
    """Checks if output contains ALL of the given strings/substrings."""

    name = "contains_all"
    description = "Checks if output contains all of the given strings"

    def __init__(self, required: List[str] = None, case_sensitive: bool = False):
        self.required = required or []
        self.case_sensitive = case_sensitive

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        required = kwargs.get("required", self.required)
        text = str(output)
        if not self.case_sensitive:
            text = text.lower()
            required = [r.lower() for r in required]

        found = [r for r in required if r in text]
        missing = [r for r in required if r not in text]
        score = len(found) / len(required) if required else 1.0
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"Found {len(found)}/{len(required)} critical items" if missing else "All required items found",
            passed=len(missing) == 0,
            metadata={"found": found, "missing": missing},
            execution_time_ms=elapsed,
        )


class CustomRubricScorer(BaseScorer):
    """Score based on any custom rubric description."""

    name = "custom_rubric"
    description = "Score based on a custom evaluation rubric"

    def __init__(self, rubric: str = "", model: str = "gpt-4o-mini"):
        self.rubric = rubric
        self.model = model

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        inp = kwargs.get("input", kwargs.get("task", {}).get("prompt", ""))

        rubric = kwargs.get("rubric", self.rubric)
        if not rubric:
            return ScorerResult(name=self.name, score=0.5, reason="No rubric provided", passed=True, execution_time_ms=0)

        prompt = f"""Evaluate the following AI output using this rubric:

RUBRIC:
{rubric}

{'INPUT: ' + inp if inp else ''}

OUTPUT:
{output}

Score (0.0 to 1.0):
Reason:"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason or "Custom rubric evaluation",
            passed=score >= kwargs.get("threshold", 0.5),
            metadata={"rubric": rubric[:100]},
            execution_time_ms=elapsed,
        )