"""Trace analyzer: quality scoring, clustering, and golden set selection."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from agent_eval.trace.schema import TraceRecord


@dataclass
class TraceQualityScore:
    """Quality assessment for a single trace."""
    trace_id: str
    overall: float = 0.0
    completeness: float = 0.0
    complexity: float = 0.0
    uniqueness: float = 0.0
    success: float = 0.0
    information: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "overall": round(self.overall, 4),
            "completeness": round(self.completeness, 4),
            "complexity": round(self.complexity, 4),
            "uniqueness": round(self.uniqueness, 4),
            "success": round(self.success, 4),
            "information": round(self.information, 4),
        }


@dataclass
class AnalysisReport:
    """Report from analyzing a collection of traces."""
    total: int = 0
    success_rate: float = 0.0
    type_distribution: Dict[str, int] = field(default_factory=dict)
    agent_distribution: Dict[str, int] = field(default_factory=dict)
    avg_duration_ms: float = 0.0
    avg_quality: float = 0.0
    avg_tool_calls: float = 0.0
    avg_turns: float = 0.0
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    intent_clusters: Dict[str, int] = field(default_factory=dict)
    error_patterns: List[Dict[str, Any]] = field(default_factory=list)
    tool_usage: Dict[str, int] = field(default_factory=dict)
    top_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "success_rate": round(self.success_rate, 4),
            "type_distribution": self.type_distribution,
            "agent_distribution": self.agent_distribution,
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "avg_quality": round(self.avg_quality, 4),
            "avg_tool_calls": round(self.avg_tool_calls, 2),
            "avg_turns": round(self.avg_turns, 2),
            "quality_distribution": self.quality_distribution,
            "intent_clusters": self.intent_clusters,
            "error_patterns": self.error_patterns,
            "tool_usage": self.tool_usage,
            "top_errors": self.top_errors,
        }


class TraceAnalyzer:
    """Analyzes trace collections for quality and patterns."""

    def analyze(self, traces: List[TraceRecord]) -> AnalysisReport:
        """Full analysis of a trace collection."""
        if not traces:
            return AnalysisReport()

        quality_scores = self.score_quality(traces)
        for trace, qs in zip(traces, quality_scores):
            trace.quality_score = qs.overall

        type_dist: Dict[str, int] = {}
        agent_dist: Dict[str, int] = {}
        durations: List[int] = []
        tool_counter: Counter = Counter()

        for t in traces:
            type_dist[t.trace_type] = type_dist.get(t.trace_type, 0) + 1
            agent_dist[t.agent_name] = agent_dist.get(t.agent_name, 0) + 1
            durations.append(t.duration_ms)
            for tc in t.tool_calls:
                tool_counter[tc.name] += 1

        quality_dist = self._quality_distribution(quality_scores)
        intent_clusters = self._cluster_by_intent(traces)
        error_patterns = self._find_error_patterns(traces)
        top_errors = list({t.error for t in traces if t.error})[:10]

        return AnalysisReport(
            total=len(traces),
            success_rate=sum(1 for t in traces if t.success) / len(traces),
            type_distribution=type_dist,
            agent_distribution=agent_dist,
            avg_duration_ms=sum(durations) / len(durations) if durations else 0,
            avg_quality=sum(q.overall for q in quality_scores) / len(quality_scores),
            avg_tool_calls=sum(t.num_tool_calls for t in traces) / len(traces),
            avg_turns=sum(t.num_turns for t in traces) / len(traces),
            quality_distribution=quality_dist,
            intent_clusters=intent_clusters,
            error_patterns=error_patterns,
            tool_usage=dict(tool_counter.most_common(20)),
            top_errors=top_errors,
        )

    def score_quality(self, traces: List[TraceRecord]) -> List[TraceQualityScore]:
        """Score each trace on multiple quality dimensions."""
        input_hashes: Dict[str, int] = {}
        for t in traces:
            h = hashlib.sha256(t.input.encode()).hexdigest()[:16]
            input_hashes[h] = input_hashes.get(h, 0) + 1

        scores: List[TraceQualityScore] = []
        for t in traces:
            # Completeness: has input + output + optionally trajectory
            completeness = 0.0
            if t.input:
                completeness += 0.3
            if t.output:
                completeness += 0.4
            if t.messages and len(t.messages) >= 2:
                completeness += 0.15
            if t.trajectory:
                completeness += 0.15

            # Complexity: steps + tools + turns
            complexity = min(1.0, (
                len(t.trajectory) * 0.1 +
                t.num_tool_calls * 0.15 +
                t.num_turns * 0.1
            ))

            # Uniqueness: how distinct is this trace's input
            h = hashlib.sha256(t.input.encode()).hexdigest()[:16]
            freq = input_hashes.get(h, 1)
            uniqueness = 1.0 / freq

            # Success
            success = 1.0 if t.success else 0.0

            # Information: output length (normalized)
            output_len = len(t.output)
            information = min(1.0, output_len / 500.0) if output_len > 0 else 0.0

            overall = (
                completeness * 0.3 +
                complexity * 0.2 +
                uniqueness * 0.15 +
                success * 0.2 +
                information * 0.15
            )

            scores.append(TraceQualityScore(
                trace_id=t.trace_id,
                overall=overall,
                completeness=completeness,
                complexity=complexity,
                uniqueness=uniqueness,
                success=success,
                information=information,
            ))

        return scores

    @staticmethod
    def _quality_distribution(scores: List[TraceQualityScore]) -> Dict[str, int]:
        buckets = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for s in scores:
            if s.overall >= 0.8:
                buckets["excellent"] += 1
            elif s.overall >= 0.6:
                buckets["good"] += 1
            elif s.overall >= 0.4:
                buckets["fair"] += 1
            else:
                buckets["poor"] += 1
        return buckets

    @staticmethod
    def _cluster_by_intent(traces: List[TraceRecord]) -> Dict[str, int]:
        """Cluster traces by simple keyword-based intent detection."""
        intent_keywords: Dict[str, Set[str]] = {
            "code_generation": {"code", "function", "implement", "write", "program", "debug", "class"},
            "question_answering": {"what", "why", "how", "when", "where", "explain", "tell"},
            "tool_use": {"search", "find", "call", "api", "query", "fetch", "lookup"},
            "summarization": {"summarize", "summary", "condense", "tldr", "brief"},
            "translation": {"translate", "translation", "convert"},
            "creative": {"write", "story", "poem", "creative", "imagine", "design"},
            "data_analysis": {"analyze", "data", "chart", "statistics", "calculate", "compute"},
        }

        clusters: Dict[str, int] = {}
        for t in traces:
            text_lower = t.input.lower()
            best_intent = "other"
            best_score = 0
            for intent, keywords in intent_keywords.items():
                score = sum(1 for kw in keywords if kw in text_lower)
                if score > best_score:
                    best_score = score
                    best_intent = intent
            clusters[best_intent] = clusters.get(best_intent, 0) + 1

        return dict(sorted(clusters.items(), key=lambda x: -x[1]))

    @staticmethod
    def _find_error_patterns(traces: List[TraceRecord]) -> List[Dict[str, Any]]:
        """Identify common error patterns in failed traces."""
        failed = [t for t in traces if not t.success and t.error]
        if not failed:
            return []

        error_words: Counter = Counter()
        for t in failed:
            words = t.error.lower().split()
            for w in words:
                if len(w) > 3:
                    error_words[w] += 1

        patterns: List[Dict[str, Any]] = []
        for word, count in error_words.most_common(10):
            if count >= 2:
                examples = [t.trace_id for t in failed if word in (t.error or "").lower()][:3]
                patterns.append({
                    "keyword": word,
                    "count": count,
                    "examples": examples,
                })
        return patterns

    def select_golden_set(
        self,
        traces: List[TraceRecord],
        n: int = 50,
        strategy: str = "diverse",
    ) -> List[TraceRecord]:
        """Select a high-quality golden set from traces.

        Strategies:
          - "diverse": maximize intent coverage + quality
          - "hard": select most complex successful traces
          - "failure": select failed traces (for regression testing)
          - "balanced": even sampling across trace types
        """
        scores = self.score_quality(traces)
        score_map = {s.trace_id: s for s in scores}

        if strategy == "failure":
            failed = [t for t in traces if not t.success]
            if len(failed) <= n:
                return failed
            return sorted(failed, key=lambda t: score_map[t.trace_id].complexity, reverse=True)[:n]

        successful = [t for t in traces if t.success]
        if not successful:
            successful = traces

        if strategy == "hard":
            return sorted(
                successful,
                key=lambda t: score_map[t.trace_id].complexity,
                reverse=True,
            )[:n]

        if strategy == "balanced":
            by_type: Dict[str, List[TraceRecord]] = {}
            for t in successful:
                by_type.setdefault(t.trace_type, []).append(t)
            per_type = max(1, n // len(by_type)) if by_type else n
            result: List[TraceRecord] = []
            for ttype, group in by_type.items():
                group_sorted = sorted(
                    group,
                    key=lambda t: score_map[t.trace_id].overall,
                    reverse=True,
                )
                result.extend(group_sorted[:per_type])
            return result[:n]

        # "diverse" (default): maximize unique intents + quality
        clusters = self._cluster_by_intent(successful)
        per_cluster = max(1, n // len(clusters)) if clusters else n
        result: List[TraceRecord] = []
        intent_keywords = self._build_intent_keywords()

        for intent in clusters:
            matching: List[Tuple[float, TraceRecord]] = []
            for t in successful:
                text_lower = t.input.lower()
                kws = intent_keywords.get(intent, set())
                if any(kw in text_lower for kw in kws) or intent == "other":
                    score = score_map[t.trace_id].overall
                    matching.append((score, t))
            matching.sort(key=lambda x: -x[0])
            result.extend([t for _, t in matching[:per_cluster]])

        # Fill remaining slots with highest quality
        if len(result) < n:
            remaining_ids = {t.trace_id for t in result}
            extra = sorted(
                [t for t in successful if t.trace_id not in remaining_ids],
                key=lambda t: score_map[t.trace_id].overall,
                reverse=True,
            )
            result.extend(extra[: n - len(result)])

        return result[:n]

    @staticmethod
    def _build_intent_keywords() -> Dict[str, Set[str]]:
        return {
            "code_generation": {"code", "function", "implement", "write", "program", "debug"},
            "question_answering": {"what", "why", "how", "when", "explain", "tell"},
            "tool_use": {"search", "find", "call", "api", "query", "fetch"},
            "summarization": {"summarize", "summary", "condense", "tldr"},
            "translation": {"translate", "translation", "convert"},
            "creative": {"story", "poem", "creative", "imagine", "design"},
            "data_analysis": {"analyze", "data", "chart", "statistics", "calculate"},
        }
