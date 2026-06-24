"""Services backing the Web UI."""

import os
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_eval.config import EvaluationConfig, parse_config
from agent_eval.orchestrator import EvaluationOrchestrator, ResultStore
from agent_eval.plugins.base import PluginRegistry
from agent_eval.plugins.custom_eval_plugin import validate_custom_eval_config
from agent_eval.reporting import ReportGenerator
from agent_eval.runner import run_evaluation_from_config
from agent_eval.trace.schema import TraceRecord
from agent_eval.trace.store import TraceStore
from agent_eval.trace.task_generator import TaskGenerator
from agent_eval.web.events import EventBus
from agent_eval.web.eval_model import EvalModelConfigStore
from agent_eval.web.langfuse import LangfuseClient, LangfuseConfigStore, langfuse_trace_to_task
from agent_eval.web.settings import WebSettingsStore


VALID_STORAGE_TYPES = {"json", "sqlite", "memory"}
VALID_REPORT_FORMATS = {"json", "html", "markdown"}


class RunManager:
    def __init__(self, event_bus: EventBus, output_dir: str = "./eval_results"):
        self.event_bus = event_bus
        self.output_dir = output_dir
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_run(
        self,
        config: EvaluationConfig,
        agent_spec: Optional[str],
        plugin_names: Optional[List[str]],
        output_dir: str,
    ) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        now = _now()
        state = {
            "run_id": run_id,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "progress": {"total": 0, "pending": 0, "running": 0, "completed": 0, "failed": 0},
            "current_plugin": None,
            "summary": None,
            "error": None,
            "report_id": None,
            "generated_reports": {},
        }
        with self._lock:
            self._runs[run_id] = state
        self.event_bus.create_run(run_id)
        self.event_bus.publish(run_id, "run_queued", {"status": "queued"})
        thread = threading.Thread(
            target=self._run_background,
            args=(run_id, config, agent_spec, plugin_names, output_dir),
            daemon=True,
        )
        thread.start()
        return state

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._runs.get(run_id)
            return dict(state) if state else None

    def _run_background(
        self,
        run_id: str,
        config: EvaluationConfig,
        agent_spec: Optional[str],
        plugin_names: Optional[List[str]],
        output_dir: str,
    ) -> None:
        orchestrator = EvaluationOrchestrator(config.orchestrator)
        self.event_bus.attach_orchestrator_hooks(run_id, orchestrator)
        _attach_progress_hooks(run_id, orchestrator, self._update_run)
        self._update_run(run_id, status="running", started_at=_now())
        try:
            result = run_evaluation_from_config(
                config,
                agent_spec=agent_spec,
                plugin_names=plugin_names,
                output_dir=output_dir,
                orchestrator=orchestrator,
            )
            self._update_run(
                run_id,
                status="completed",
                completed_at=_now(),
                summary=result.report.summary,
                report_id=result.report.run_id,
                generated_reports=result.generated_reports,
            )
        except Exception as exc:
            self._update_run(run_id, status="failed", completed_at=_now(), error=str(exc))
            self.event_bus.publish(run_id, "evaluation_failed", {"error": str(exc)})

    def _update_run(self, run_id: str, **updates) -> None:
        with self._lock:
            if run_id not in self._runs:
                return
            for key, value in updates.items():
                if key == "progress":
                    self._runs[run_id]["progress"].update(value)
                else:
                    self._runs[run_id][key] = value


class WebService:
    def __init__(self, output_dir: str = "./eval_results", workspace: str = None, trace_dir: str = "./traces"):
        self.output_dir = output_dir
        self.workspace = os.path.abspath(workspace or os.getcwd())
        self.trace_dir = trace_dir
        self.event_bus = EventBus()
        self.runs = RunManager(self.event_bus, output_dir)
        self.langfuse_config = LangfuseConfigStore(self.workspace)
        self.langfuse_client = LangfuseClient(self.langfuse_config)
        self.settings_store = WebSettingsStore(self.workspace)
        self.eval_model_config = EvalModelConfigStore(self.workspace)

    def validate_config(self, raw_config: Dict[str, Any]) -> Dict[str, Any]:
        errors = []
        warnings = []
        normalized = {}
        config = None
        try:
            config = parse_config(raw_config)
            normalized = asdict(config)
        except Exception as exc:
            errors.append({"field": "config", "message": str(exc)})

        if config:
            if config.orchestrator.max_workers <= 0:
                errors.append({"field": "orchestrator.max_workers", "message": "must be greater than 0"})
            storage_type = config.orchestrator.storage.get("type", "json")
            if storage_type not in VALID_STORAGE_TYPES:
                errors.append({"field": "orchestrator.storage.type", "message": f"unsupported storage type: {storage_type}"})
            for fmt in config.report.get("formats", []):
                if fmt not in VALID_REPORT_FORMATS:
                    errors.append({"field": "report.formats", "message": f"unsupported report format: {fmt}"})
            available_plugins = PluginRegistry.list_plugins()
            for name, plugin_config in config.plugins.items():
                if name not in available_plugins:
                    errors.append({"field": f"plugins.{name}", "message": "plugin is not registered"})
                if name == "custom_eval":
                    errors.extend(validate_custom_eval_config(plugin_config.config, workspace=self.workspace))
            if not config.agent.module and not config.agent.config.get("model"):
                warnings.append({"field": "agent", "message": "no agent module or model configured; provide agent when starting a run"})

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "normalized": normalized,
        }

    def read_config_file(self, path: str) -> Dict[str, Any]:
        abs_path = self._safe_path(path)
        from agent_eval.config import load_config

        config = load_config(abs_path)
        with open(abs_path) as file:
            raw = file.read()
        return {"path": abs_path, "config": asdict(config), "raw": raw}

    def result_store(self, output_dir: str = None) -> ResultStore:
        return ResultStore({"type": "json", "output_dir": output_dir or self.output_dir})

    def generate_report(self, run_id: str, formats: List[str], output_dir: str) -> Dict[str, str]:
        store = self.result_store(output_dir)
        report = store.load(run_id)
        if report is None:
            raise KeyError(run_id)
        return ReportGenerator(output_dir).generate(report, formats)

    def compare_reports(self, run_ids: List[str], output_dir: str) -> Dict[str, Any]:
        store = self.result_store(output_dir)
        comparison = store.compare(run_ids)
        reports = [report.to_dict() for report in comparison["reports"]]
        return {
            "reports": reports,
            "comparison": comparison["comparison"],
            "overall_scores": {report["run_id"]: report["summary"].get("overall_score", 0) for report in reports},
            "pass_rates": {report["run_id"]: report["summary"].get("pass_rate", 0) for report in reports},
        }

    def trace_store(self) -> TraceStore:
        return TraceStore(path=self.trace_dir)

    def list_traces(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = self.trace_store().query({key: value for key, value in filters.items() if value is not None})
        return [self._trace_summary(record) for record in records]

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        record = self.trace_store().load(trace_id)
        return record.to_dict() if record else None

    def build_trace_eval_config(
        self,
        trace_ids: List[str],
        scorers: List[str],
        eval_id: str,
        name: str,
        dimensions: List[str],
        threshold: float,
        aggregation: str,
    ) -> Dict[str, Any]:
        store = self.trace_store()
        traces: List[TraceRecord] = []
        for trace_id in trace_ids:
            trace = store.load(trace_id)
            if trace is None:
                raise KeyError(trace_id)
            traces.append(trace)

        tasks = TaskGenerator().generate_batch(traces)
        selected_scorers = scorers or sorted({scorer for task in tasks for scorer in task.scorers})
        selected_dimensions = dimensions or ["custom"]
        primary_dimension = selected_dimensions[0]
        items = []
        for task in tasks:
            item = task.to_dict()
            item["expected"] = item.pop("expected_output", "")
            items.append(item)

        return {
            "enabled": True,
            "evaluations": [
                {
                    "id": eval_id,
                    "name": name,
                    "description": "Generated from selected execution traces.",
                    "dimensions": selected_dimensions,
                    "task_source": {"type": "inline", "items": items},
                    "prompt": {"mode": "generate", "template": "{input}"},
                    "scoring": {
                        "threshold": threshold,
                        "aggregation": aggregation,
                        "scorers": [
                            {
                                "id": scorer,
                                "type": scorer,
                                "weight": 1,
                                "dimension": primary_dimension,
                                "params": {},
                            }
                            for scorer in selected_scorers
                        ],
                    },
                    "metadata": {"source_trace_ids": trace_ids},
                }
            ],
        }

    def get_settings(self) -> Dict[str, Any]:
        settings = self.settings_store.load()
        return {
            **settings,
            "trace": {"trace_dir": self.trace_dir},
            "langfuse": self.langfuse_config.load_masked(),
            "eval_model": self.eval_model_config.load_masked(),
        }

    def save_settings(self, update: Dict[str, Any]) -> Dict[str, Any]:
        self.settings_store.save({"run_defaults": update.get("run_defaults", {})})
        if "langfuse" in update:
            self.langfuse_config.save(update["langfuse"])
        if "eval_model" in update:
            self.eval_model_config.save(update["eval_model"])
        return self.get_settings()

    def get_langfuse_config(self) -> Dict[str, Any]:
        return self.langfuse_config.load_masked()

    def save_langfuse_config(self, update: Dict[str, Any]) -> Dict[str, Any]:
        return self.langfuse_config.save(update)

    def test_langfuse_connection(self) -> Dict[str, Any]:
        return self.langfuse_client.test_connection()

    def list_langfuse_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.langfuse_client.fetch_sessions(limit=limit)

    def list_langfuse_session_traces(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.langfuse_client.fetch_session_traces(session_id, limit=limit)

    def get_langfuse_trace(self, trace_id: str) -> Dict[str, Any]:
        return self.langfuse_client.fetch_trace(trace_id)

    def build_langfuse_eval_config(
        self,
        trace_ids: List[str],
        scorers: List[str],
        eval_id: str,
        name: str,
        dimensions: List[str],
        threshold: float,
        aggregation: str,
    ) -> Dict[str, Any]:
        selected_dimensions = dimensions or ["custom"]
        primary_dimension = selected_dimensions[0]
        items = [langfuse_trace_to_task(self.langfuse_client.fetch_trace(trace_id)) for trace_id in trace_ids]
        return {
            "enabled": True,
            "evaluations": [
                {
                    "id": eval_id,
                    "name": name,
                    "description": "Generated from selected Langfuse traces.",
                    "dimensions": selected_dimensions,
                    "task_source": {"type": "inline", "items": items},
                    "prompt": {"mode": "generate", "template": "{input}"},
                    "scoring": {
                        "threshold": threshold,
                        "aggregation": aggregation,
                        "scorers": [
                            {
                                "id": scorer,
                                "type": scorer,
                                "weight": 1,
                                "dimension": primary_dimension,
                                "params": {},
                            }
                            for scorer in scorers
                        ],
                    },
                    "metadata": {"source": "langfuse", "source_trace_ids": trace_ids},
                }
            ],
        }

    @staticmethod
    def _trace_summary(record: TraceRecord) -> Dict[str, Any]:
        return {
            "trace_id": record.trace_id,
            "timestamp": record.timestamp,
            "agent_name": record.agent_name,
            "trace_type": record.trace_type,
            "success": record.success,
            "quality_score": record.quality_score,
            "duration_ms": record.duration_ms,
            "tags": record.tags,
            "num_tool_calls": record.num_tool_calls,
            "num_turns": record.num_turns,
        }

    def _safe_path(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        if os.path.commonpath([self.workspace, abs_path]) != self.workspace:
            raise ValueError("path is outside the configured workspace")
        return abs_path


def _attach_progress_hooks(run_id: str, orchestrator: EvaluationOrchestrator, update_run) -> None:
    def on_task_generated(plugin, tasks):
        current = orchestrator.task_queue.progress()
        update_run(run_id, current_plugin=plugin.name, progress=current)

    def on_task_execute(plugin, task):
        current = orchestrator.task_queue.progress()
        update_run(run_id, current_plugin=plugin.name, progress=current)

    def on_task_complete(task_id, result):
        state = update_run
        current = orchestrator.task_queue.progress()
        state(run_id, progress={"completed": current.get("completed", 0), "failed": current.get("failed", 0)})

    def on_task_failed(task_id, error):
        current = orchestrator.task_queue.progress()
        update_run(run_id, progress={"completed": current.get("completed", 0), "failed": current.get("failed", 0)})

    orchestrator.hooks.register("task_generated", on_task_generated)
    orchestrator.hooks.register("task_execute", on_task_execute)
    orchestrator.hooks.register("task_complete", on_task_complete)
    orchestrator.hooks.register("task_failed", on_task_failed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
