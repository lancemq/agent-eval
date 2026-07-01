"""Trace collector: captures agent execution traces from hooks or manual submission."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from agent_eval.trace.schema import TraceRecord, TraceStep, ToolCallSummary
from agent_eval.trace.store import TraceStore
from agent_eval.trace.normalizers import (
    auto_detect_normalizer, get_normalizer,
    SelfEvalNormalizer,
)


class TraceBuilder:
    """Context manager for building a trace during live agent execution.

    Usage:
        collector = TraceCollector(store)
        with collector.trace(agent_name="my_agent", trace_type="tool_use") as tb:
            tb.set_input("What's the weather?")
            tb.add_tool_call("weather_api", {"city": "SF"}, "72F sunny")
            tb.set_output("It's 72F and sunny in SF.")
    """

    def __init__(self, collector: "TraceCollector", trace_id: str, agent_name: str, trace_type: str):
        self._collector = collector
        self._record = TraceRecord(
            trace_id=trace_id,
            agent_name=agent_name,
            trace_type=trace_type,
            source="live",
        )
        self._start_time = time.time()
        self._step_index = 0

    def __enter__(self) -> "TraceBuilder":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self._record.success = False
            self._record.error = str(exc_val)
        self._record.duration_ms = int((time.time() - self._start_time) * 1000)
        if self._record.trace_type == "single_turn" and self._record.trajectory:
            self._record.trace_type = self._record.infer_type()
        self._collector.save(self._record)

    def set_input(self, text: str) -> "TraceBuilder":
        self._record.input = text
        return self

    def set_output(self, text: str) -> "TraceBuilder":
        self._record.output = text
        return self

    def add_message(self, role: str, content: str) -> "TraceBuilder":
        self._record.messages.append({"role": role, "content": content})
        return self

    def add_tool_call(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        result: Any = None,
        success: bool = True,
        duration_ms: int = 0,
    ) -> "TraceBuilder":
        tc = ToolCallSummary(
            name=name, arguments=arguments or {}, result=result,
            success=success, duration_ms=duration_ms,
        )
        self._record.tool_calls.append(tc)
        self._add_step("tool_call", {"tool": name, "params": arguments or {}}, result)
        return self

    def add_llm_call(
        self, prompt: str, response: str, duration_ms: int = 0,
    ) -> "TraceBuilder":
        self._add_step("llm_call", {"prompt": prompt[:500]}, response[:500], duration_ms=duration_ms)
        return self

    def add_step(
        self,
        action_type: str,
        action: Optional[Dict] = None,
        result: Any = None,
    ) -> "TraceBuilder":
        self._add_step(action_type, action or {}, result)
        return self

    def set_metadata(self, key: str, value: Any) -> "TraceBuilder":
        self._record.metadata[key] = value
        return self

    def add_tag(self, tag: str) -> "TraceBuilder":
        if tag not in self._record.tags:
            self._record.tags.append(tag)
        return self

    def set_success(self, success: bool) -> "TraceBuilder":
        self._record.success = success
        return self

    def _add_step(self, action_type: str, action: Dict, result: Any, duration_ms: int = 0) -> None:
        self._record.trajectory.append(TraceStep(
            step_index=self._step_index,
            action_type=action_type,
            action=action,
            result=result,
            duration_ms=duration_ms,
        ))
        self._step_index += 1


class TraceCollector:
    """Collects and stores agent execution traces.

    Usage 1 - Hook-based (auto-capture from orchestrator):
        collector = TraceCollector(store=store)
        orch.hooks.on("task_complete", collector.on_task_complete)

    Usage 2 - Context manager (manual capture):
        with collector.trace(agent_name="my_agent") as tb:
            tb.set_input("hello")
            tb.set_output("hi there")

    Usage 3 - Import from files:
        collector.import_dir("./logs", source="custom")
    """

    def __init__(self, store: Optional[TraceStore] = None, config: Optional[Dict] = None):
        self.store = store or TraceStore()
        self.config = config or {}

    def trace(
        self,
        agent_name: str = "unknown",
        trace_type: str = "single_turn",
        trace_id: str = "",
    ) -> TraceBuilder:
        """Start a new trace context."""
        return TraceBuilder(
            collector=self,
            trace_id=trace_id or str(uuid.uuid4()),
            agent_name=agent_name,
            trace_type=trace_type,
        )

    def save(self, record: TraceRecord) -> str:
        """Save a trace record."""
        return self.store.save(record)

    def submit(self, record: TraceRecord) -> str:
        """Alias for save()."""
        return self.save(record)

    def submit_raw(self, raw_data: Dict[str, Any], source: str = "auto") -> str:
        """Submit raw data, auto-normalizing to TraceRecord."""
        if source == "auto":
            normalizer = auto_detect_normalizer(raw_data)
        else:
            normalizer = get_normalizer(source)
        record = normalizer.normalize(raw_data)
        return self.save(record)

    def on_task_complete(self, task_id: str, result: Any) -> None:
        """Hook callback: extract trace from EvalResult."""
        normalizer = SelfEvalNormalizer()
        raw = result
        if hasattr(result, "to_dict"):
            raw = result.to_dict()
        elif not isinstance(result, dict):
            raw = {"task_id": task_id, "details": {"output": str(result)}}
        raw["task_id"] = task_id
        try:
            record = normalizer.normalize(raw)
            self.save(record)
        except Exception:
            pass

    def import_dir(self, dir_path: str, source: str = "auto") -> int:
        """Import trace files from a directory."""
        count = 0
        for fname in os.listdir(dir_path):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(dir_path, fname)) as f:
                    raw = json.load(f)
                self.submit_raw(raw, source=source)
                count += 1
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return count

    def import_eval_results(self, results_dir: str, min_score: float = 0.0) -> int:
        """Import from AgentEval result JSON files."""
        count = 0
        normalizer = SelfEvalNormalizer()
        for fname in os.listdir(results_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(results_dir, fname)) as f:
                    report = json.load(f)
                task_results = report.get("task_results", {})
                for evaluator_name, results in task_results.items():
                    for r in results:
                        if r.get("score", 0) >= min_score:
                            r["agent_name"] = report.get("agent", {}).get("name", "unknown")
                            record = normalizer.normalize(r)
                            self.save(record)
                            count += 1
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return count
