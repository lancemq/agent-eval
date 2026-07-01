"""Trace package - end-to-end trace recording, analysis, and replay."""

from agent_eval.trace.schema import TraceRecord, TraceStep, ToolCallSummary
from agent_eval.trace.store import TraceStore
from agent_eval.trace.collector import TraceCollector, TraceBuilder
from agent_eval.trace.normalizers import (
    BaseTraceNormalizer, CustomJSONNormalizer, SelfEvalNormalizer,
    OpenTelemetryNormalizer, LangSmithNormalizer,
    get_normalizer, auto_detect_normalizer, list_normalizers,
)
from agent_eval.trace.task_generator import TaskGenerator, EvalTask
from agent_eval.trace.analyzer import TraceAnalyzer, AnalysisReport, TraceQualityScore
from agent_eval.trace.replay import TracePlayer

__all__ = [
    "TraceRecord", "TraceStep", "ToolCallSummary",
    "TraceStore", "TraceCollector", "TraceBuilder",
    "BaseTraceNormalizer", "CustomJSONNormalizer", "SelfEvalNormalizer",
    "OpenTelemetryNormalizer", "LangSmithNormalizer",
    "get_normalizer", "auto_detect_normalizer", "list_normalizers",
    "TaskGenerator", "EvalTask",
    "TraceAnalyzer", "AnalysisReport", "TraceQualityScore",
    "TracePlayer",
]
