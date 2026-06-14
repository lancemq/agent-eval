"""Format validation scorers: datetime, URL, email, markdown, citations, instruction following."""

from __future__ import annotations

import re
from typing import List
from agent_eval.scorers.base import BaseScorer, ScorerResult


class DateTimeFormatScorer(BaseScorer):
    """Validates that output is a properly formatted date/time string."""

    name = "datetime_format"
    description = "Date/time format validation"

    COMMON_FORMATS = [
        r"\d{4}-\d{2}-\d{2}",                                           # 2024-01-15
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",                         # ISO 8601
        r"\d{4}/\d{2}/\d{2}",                                           # 2024/01/15
        r"\d{2}/\d{2}/\d{4}",                                           # 01/15/2024
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?",                   # 2024-01-15 14:30
        r"\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}",  # 15 January 2024
    ]

    def __init__(self, pattern: str = ""):
        self.custom_pattern = pattern

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output).strip()
        pattern = kwargs.get("pattern", self.custom_pattern)

        if pattern:
            matched = bool(re.fullmatch(pattern, text))
            reason = f"Custom pattern {'matched' if matched else 'not matched'}"
        else:
            matched = any(re.search(fmt, text) for fmt in self.COMMON_FORMATS)
            reason = f"{'Valid' if matched else 'Invalid'} date/time format"

        score = 1.0 if matched else 0.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=score, reason=reason, passed=matched,
            metadata={"value": text}, execution_time_ms=elapsed,
        )


class URLFormatScorer(BaseScorer):
    """Validates URL format including protocol, domain, and optional path."""

    name = "url_format"
    description = "URL format validation (http/https/ftp)"

    URL_REGEX = re.compile(
        r"^https?://"
        r"[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9]?\.)*"
        r"[a-zA-Z]{2,}"
        r"(:\d+)?"
        r"(/[^\s]*)?$",
        re.IGNORECASE,
    )

    def __init__(self, require_https: bool = False):
        self.require_https = require_https

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output).strip()
        matched = bool(self.URL_REGEX.match(text))

        if matched and self.require_https:
            matched = text.lower().startswith("https://")
            if not matched:
                return ScorerResult(
                    name=self.name, score=0.0,
                    reason="URL valid but not HTTPS", passed=False,
                    execution_time_ms=int((time.time() - start) * 1000),
                )

        score = 1.0 if matched else 0.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=score,
            reason=f"{'Valid' if matched else 'Invalid'} URL format",
            passed=matched, metadata={"url": text[:100]},
            execution_time_ms=elapsed,
        )


class EmailFormatScorer(BaseScorer):
    """Validates email address format."""

    name = "email_format"
    description = "Email address format validation"

    EMAIL_REGEX = re.compile(
        r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$",
        re.IGNORECASE,
    )

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output).strip()
        matched = bool(self.EMAIL_REGEX.match(text))
        score = 1.0 if matched else 0.0
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=score,
            reason=f"{'Valid' if matched else 'Invalid'} email format",
            passed=matched, metadata={"email": text[:100]},
            execution_time_ms=elapsed,
        )


class MarkdownStructureScorer(BaseScorer):
    """Validates markdown structure: headings, lists, code blocks, links."""

    name = "markdown_structure"
    description = "Markdown structure validation (headings, lists, code blocks)"

    def __init__(
        self,
        require_headings: bool = False,
        require_code_block: bool = False,
        require_list: bool = False,
        min_headings: int = 0,
    ):
        self.require_headings = require_headings
        self.require_code_block = require_code_block
        self.require_list = require_list
        self.min_headings = min_headings

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output)
        issues: List[str] = []

        headings = re.findall(r"^#{1,6}\s+\S+", text, re.MULTILINE)
        code_blocks = re.findall(r"```\w*\n[\s\S]*?```", text)
        lists = re.findall(r"^\s*[-*+]\s+\S+|^\s*\d+\.\s+\S+", text, re.MULTILINE)
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
        images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)

        if self.require_headings and not headings:
            issues.append("missing headings")
        if self.min_headings > 0 and len(headings) < self.min_headings:
            issues.append(f"only {len(headings)} headings (need {self.min_headings})")
        if self.require_code_block and not code_blocks:
            issues.append("missing code block")
        if self.require_list and not lists:
            issues.append("missing list")

        # Check for unclosed code blocks
        fence_count = text.count("```")
        if fence_count % 2 != 0:
            issues.append("unclosed code block (odd number of ```)")

        score = max(0.0, 1.0 - len(issues) * 0.3)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(issues) if issues else 'Markdown structure OK'}",
            passed=score >= kwargs.get("threshold", 0.6),
            metadata={"headings": len(headings), "code_blocks": len(code_blocks),
                      "lists": len(lists), "links": len(links), "images": len(images)},
            execution_time_ms=elapsed,
        )


class CitationCheckScorer(BaseScorer):
    """Checks for proper citations/references in the output.

    Detects: inline citations [1], (Author, Year), footnotes,
    bibliography sections, DOI/URL references.
    """

    name = "citation_check"
    description = "Citation/reference presence and format validation"

    CITATION_PATTERNS = [
        (r"\[(\d+)\]", "numeric bracket [1]"),
        (r"\(([\w\s]+,\s*\d{4})\)", "author-year (Author, 2024)"),
        (r"\(\d{4}[a-z]?\)", "year-only (2024)"),
        (r"\bdoi:\s*\S+", "DOI reference"),
        (r"https?://\S+", "URL reference"),
    ]

    def __init__(self, min_citations: int = 1):
        self.min_citations = min_citations

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        text = str(output)
        total_citations = 0
        found_types: List[str] = []

        for pattern, cite_type in self.CITATION_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                total_citations += len(matches)
                found_types.append(f"{cite_type} ({len(matches)})")

        # Check for bibliography/references section
        has_bibliography = bool(
            re.search(r"\n#{1,3}\s*(References|Bibliography|Sources|Citations)", text, re.IGNORECASE)
        )
        if has_bibliography:
            total_citations = max(total_citations, 1)

        score = min(1.0, total_citations / self.min_citations) if self.min_citations > 0 else (1.0 if total_citations > 0 else 0.0)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{total_citations} citations found: {', '.join(found_types) if found_types else 'none'}",
            passed=total_citations >= self.min_citations,
            metadata={"total_citations": total_citations, "citation_types": found_types,
                      "has_bibliography": has_bibliography},
            execution_time_ms=elapsed,
        )


class InstructionFollowingScorer(BaseScorer):
    """Checks if the output follows specific formatting instructions.

    Detects compliance with common instruction patterns:
    - "answer in JSON/XML/CSV format"
    - "use bullet points / numbered list"
    - "respond in less than N words/sentences"
    - "include/exclude specific keywords"
    - "answer in uppercase/lowercase"
    """

    name = "instruction_following"
    description = "Check if output follows formatting instructions"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        instruction = kwargs.get("instruction", kwargs.get("input", ""))
        text = str(output)
        checks: List[str] = []
        failures: List[str] = []

        inst_lower = instruction.lower() if isinstance(instruction, str) else ""

        # Format checks
        if "json" in inst_lower:
            import json as json_mod
            try:
                json_mod.loads(text.strip())
                checks.append("JSON format")
            except Exception:
                failures.append("expected JSON format")

        if "xml" in inst_lower:
            if text.strip().startswith("<") and text.strip().endswith(">"):
                checks.append("XML format")
            else:
                failures.append("expected XML format")

        if "bullet" in inst_lower or "unordered list" in inst_lower:
            if re.search(r"^\s*[-*+]\s+\S+", text, re.MULTILINE):
                checks.append("bullet list")
            else:
                failures.append("expected bullet list")

        if "numbered list" in inst_lower or "ordered list" in inst_lower:
            if re.search(r"^\s*\d+\.\s+\S+", text, re.MULTILINE):
                checks.append("numbered list")
            else:
                failures.append("expected numbered list")

        # Word count constraint
        wc_match = re.search(r"(?:less than|under|at most|max(?:imum)?)\s+(\d+)\s+words?", inst_lower)
        if wc_match:
            limit = int(wc_match.group(1))
            actual = len(text.split())
            if actual <= limit:
                checks.append(f"word count {actual}/{limit}")
            else:
                failures.append(f"word count {actual} > {limit}")

        # Sentence count constraint
        sc_match = re.search(r"(?:less than|under|at most)\s+(\d+)\s+sentences?", inst_lower)
        if sc_match:
            limit = int(sc_match.group(1))
            actual = len(re.findall(r"[.!?]+", text))
            if actual <= limit:
                checks.append(f"sentences {actual}/{limit}")
            else:
                failures.append(f"sentences {actual} > {limit}")

        # Case constraints
        if "uppercase" in inst_lower or "all caps" in inst_lower:
            if text.isupper():
                checks.append("uppercase")
            else:
                failures.append("expected uppercase")

        if "lowercase" in inst_lower and "uppercase" not in inst_lower:
            if text.islower():
                checks.append("lowercase")
            else:
                failures.append("expected lowercase")

        # Keyword inclusion
        include_match = re.findall(r"include[s]?\s+['\"]([^'\"]+)['\"]", inst_lower)
        for kw in include_match:
            if kw.lower() in text.lower():
                checks.append(f"includes '{kw}'")
            else:
                failures.append(f"missing keyword '{kw}'")

        total_checks = len(checks) + len(failures)
        score = len(checks) / total_checks if total_checks > 0 else 0.5
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Passed: {checks or 'none'}. Failed: {failures or 'none'}",
            passed=len(failures) == 0 and len(checks) > 0,
            metadata={"checks_passed": checks, "checks_failed": failures},
            execution_time_ms=elapsed,
        )
