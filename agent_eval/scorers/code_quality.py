"""Code quality scorers: static analysis, SQL validation, complexity, format checks."""

from __future__ import annotations

import ast
import re
from typing import List
from agent_eval.scorers.base import BaseScorer, ScorerResult


class CodeQualityScorer(BaseScorer):
    """Evaluates Python code quality via AST analysis.

    Checks: syntax validity, import count, function/class definitions,
    docstring presence, line length, bare except, TODO/FIXME.
    """

    name = "code_quality"
    description = "Python code quality via static analysis (syntax, docstrings, complexity)"

    def __init__(self, max_line_length: int = 100):
        self.max_line_length = max_line_length

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        code = str(output)
        issues: List[str] = []
        checks_passed: List[str] = []

        # 1. Syntax validity
        try:
            tree = ast.parse(code)
            checks_passed.append("syntax_valid")
        except SyntaxError as e:
            tree = None
            issues.append(f"syntax_error: {e}")

        if tree:
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

            # 2. Docstring presence
            docstr_count = sum(1 for f in funcs if (f.body and isinstance(f.body[0], ast.Expr) and isinstance(f.body[0].value, ast.Constant) and isinstance(f.body[0].value.value, str)))
            if funcs:
                docstr_ratio = docstr_count / len(funcs)
                if docstr_ratio < 0.5:
                    issues.append(f"docstring_coverage_low: {docstr_ratio:.0%}")
                else:
                    checks_passed.append("docstrings_present")
            else:
                checks_passed.append("no_functions")

            # 3. Bare except
            bare_excepts = sum(
                1 for n in ast.walk(tree)
                if isinstance(n, ast.ExceptHandler) and n.type is None
            )
            if bare_excepts:
                issues.append(f"bare_except: {bare_excepts}")

            # 4. TODO/FIXME
            todos = len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", code, re.IGNORECASE))
            if todos:
                issues.append(f"todo_fixme: {todos}")

        # 5. Line length
        long_lines = sum(1 for line in code.split("\n") if len(line) > self.max_line_length)
        if long_lines:
            issues.append(f"long_lines: {long_lines}")

        total_checks = 5
        score = max(0.0, 1.0 - len(issues) / total_checks)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(issues) if issues else 'All checks passed'}",
            passed=score >= kwargs.get("threshold", 0.6),
            metadata={"issues": issues, "checks_passed": checks_passed,
                      "num_functions": len(funcs) if tree else 0,
                      "num_classes": len(classes) if tree else 0},
            execution_time_ms=elapsed,
        )


class SQLValidationScorer(BaseScorer):
    """Validates SQL syntax and checks for common anti-patterns."""

    name = "sql_validation"
    description = "SQL syntax validation and anti-pattern detection"

    SQL_KEYWORDS = {
        "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE",
        "DROP", "ALTER", "TABLE", "INDEX", "JOIN", "INNER", "LEFT", "RIGHT",
        "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET", "UNION", "ALL",
        "AS", "AND", "OR", "NOT", "NULL", "IS", "IN", "BETWEEN", "LIKE",
        "DISTINCT", "COUNT", "SUM", "AVG", "MIN", "MAX", "VALUES", "SET",
        "INTO", "ON", "WITH", "CASE", "WHEN", "THEN", "ELSE", "END",
    }

    DANGEROUS_PATTERNS = [
        (r";\s*DROP\s", "dangerous DROP statement"),
        (r";\s*DELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without WHERE clause"),
        (r"SELECT\s+\*\s+FROM", "SELECT * (inefficient)"),
        (r"\bEXEC\s*\(", "dynamic SQL execution"),
    ]

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        sql = str(output).strip()
        issues: List[str] = []

        # Basic validation: must contain a SQL keyword
        first_word = sql.split()[0].upper() if sql.split() else ""
        if first_word not in self.SQL_KEYWORDS:
            issues.append(f"doesn't start with SQL keyword (got '{first_word}')")

        # Check for balanced parentheses
        if sql.count("(") != sql.count(")"):
            issues.append("unbalanced parentheses")

        # Dangerous patterns
        for pattern, desc in self.DANGEROUS_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                issues.append(desc)

        # Check for semicolons (multiple statements)
        semicolons = sql.rstrip(";").count(";")
        if semicolons > 0:
            issues.append(f"multiple statements ({semicolons + 1})")

        score = max(0.0, 1.0 - len(issues) * 0.25)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(issues) if issues else 'Valid SQL'}",
            passed=score >= kwargs.get("threshold", 0.7),
            metadata={"issues": issues, "sql_length": len(sql)},
            execution_time_ms=elapsed,
        )


class CodeFormatScorer(BaseScorer):
    """Checks code formatting compliance (PEP 8 style checks)."""

    name = "code_format"
    description = "Code formatting compliance (PEP 8 style checks)"

    def __init__(self, max_line_length: int = 99):
        self.max_line_length = max_line_length

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        code = str(output)
        violations: List[str] = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            # Line length
            if len(line) > self.max_line_length:
                violations.append(f"line {i}: too long ({len(line)})")

            # Trailing whitespace
            if line != line.rstrip():
                violations.append(f"line {i}: trailing whitespace")

            # Tabs instead of spaces
            if "\t" in line:
                violations.append(f"line {i}: tab character")

            # Multiple spaces before keyword
            if re.search(r"  +(if|for|while|def|class|return)\b", line):
                violations.append(f"line {i}: extra indentation before keyword")

        # Indentation consistency
        indent_styles = set()
        for line in lines:
            if line.strip():
                leading = len(line) - len(line.lstrip())
                if leading > 0:
                    indent_styles.add("tabs" if "\t" in line[:leading] else "spaces")
        if len(indent_styles) > 1:
            violations.append("mixed tabs and spaces")

        score = max(0.0, 1.0 - len(violations) / max(len(lines), 1))
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(violations[:5]) if violations else 'Formatting OK'}",
            passed=score >= kwargs.get("threshold", 0.8),
            metadata={"violations": len(violations), "total_lines": len(lines)},
            execution_time_ms=elapsed,
        )


class CyclomaticComplexityScorer(BaseScorer):
    """Measures cyclomatic complexity of Python code via AST.

    Lower complexity = better score. Score = 1.0 when complexity is within
    acceptable range, decreasing as complexity increases.
    """

    name = "complexity"
    description = "Cyclomatic complexity of Python code (lower = better)"

    def __init__(self, max_complexity: int = 10):
        self.max_complexity = max_complexity

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        code = str(output)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ScorerResult(
                name=self.name, score=0.0,
                reason=f"Syntax error: {e}", passed=False, execution_time_ms=0,
            )

        # Count decision points: if, elif, for, while, except, and, or, with
        decision_nodes = (
            ast.If, ast.For, ast.While, ast.ExceptHandler,
            ast.BoolOp,
        )

        complexity = 1  # Base path
        for node in ast.walk(tree):
            if isinstance(node, decision_nodes):
                if isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1
                else:
                    complexity += 1

        # Normalize: score = 1.0 when complexity <= max, linearly decreasing
        if complexity <= self.max_complexity:
            score = 1.0
        else:
            score = max(0.0, 1.0 - (complexity - self.max_complexity) / max(complexity, 1))

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"Cyclomatic complexity: {complexity} (max={self.max_complexity})",
            passed=complexity <= self.max_complexity,
            metadata={"complexity": complexity, "max_complexity": self.max_complexity},
            execution_time_ms=elapsed,
        )


class CodeSecurityScorer(BaseScorer):
    """Checks Python code for common security vulnerabilities.

    Detects: eval(), exec(), os.system(), subprocess with shell=True,
    SQL injection patterns, hardcoded secrets, pickle.loads, etc.
    """

    name = "code_security"
    description = "Python code security vulnerability detection"

    DANGEROUS_PATTERNS = [
        (r"\beval\s*\(", "eval() usage"),
        (r"\bexec\s*\(", "exec() usage"),
        (r"os\.system\s*\(", "os.system() command injection risk"),
        (r"subprocess\..*shell\s*=\s*True", "subprocess shell=True injection risk"),
        (r"\bpickle\.loads?\s*\(", "pickle deserialization risk"),
        (r"\b__import__\s*\(", "dynamic import"),
        (r"yaml\.load\s*\([^)]*\)\s*$", "unsafe yaml.load (use yaml.safe_load)"),
        (r"password\s*=\s*['\"]", "hardcoded password"),
        (r"api_key\s*=\s*['\"]", "hardcoded API key"),
        (r"secret\s*=\s*['\"]", "hardcoded secret"),
        (r"token\s*=\s*['\"][^'\"]{10,}['\"]", "hardcoded token"),
    ]

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        code = str(output)
        issues: List[str] = []

        for pattern, desc in self.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, code, re.IGNORECASE | re.MULTILINE)
            if matches:
                issues.append(f"{desc} ({len(matches)}x)")

        score = max(0.0, 1.0 - len(issues) * 0.2)
        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name, score=round(score, 4),
            reason=f"{'; '.join(issues) if issues else 'No security issues found'}",
            passed=len(issues) == 0,
            metadata={"issues": issues, "num_issues": len(issues)},
            execution_time_ms=elapsed,
        )
