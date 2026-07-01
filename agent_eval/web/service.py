"""Services backing the Web UI."""

import os
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_eval.config import EvaluationConfig, parse_config
from agent_eval.orchestrator import EvaluationOrchestrator, EvaluationReport, ResultStore
from agent_eval.evaluators.base import EvaluatorRegistry
from agent_eval.evaluators.custom_eval_plugin import validate_custom_eval_config
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
        self.workspace = os.getcwd()
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set_workspace(self, workspace: str) -> None:
        self.workspace = workspace

    def create_run(
        self,
        config: EvaluationConfig,
        agent_spec: Optional[str],
        evaluator_names: Optional[List[str]],
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
            "current_evaluator": None,
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
            args=(run_id, config, agent_spec, evaluator_names, output_dir),
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
        evaluator_names: Optional[List[str]],
        output_dir: str,
    ) -> None:
        orchestrator = EvaluationOrchestrator(config.orchestrator, workspace=self.workspace)
        self.event_bus.attach_orchestrator_hooks(run_id, orchestrator)
        _attach_progress_hooks(run_id, orchestrator, self._update_run)
        self._update_run(run_id, status="running", started_at=_now())
        try:
            result = run_evaluation_from_config(
                config,
                agent_spec=agent_spec,
                evaluator_names=evaluator_names,
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
        self.runs.set_workspace(self.workspace)
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
            available_evaluators = EvaluatorRegistry.list_evaluators()
            for name, evaluator_config in config.evaluators.items():
                if name not in available_evaluators:
                    errors.append({"field": f"evaluators.{name}", "message": "evaluator is not registered"})
                if name == "custom_eval":
                    errors.extend(validate_custom_eval_config(evaluator_config.config, workspace=self.workspace))
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
        row_level = store.compare_row_level(run_ids) if len(run_ids) >= 2 else {}
        statistics = self._compute_comparison_statistics(comparison["reports"]) if len(reports) >= 2 else {}
        return {
            "reports": reports,
            "comparison": comparison["comparison"],
            "overall_scores": {report["run_id"]: report["summary"].get("overall_score", 0) for report in reports},
            "pass_rates": {report["run_id"]: report["summary"].get("pass_rate", 0) for report in reports},
            "row_level": row_level,
            "statistics": statistics,
        }

    def _compute_comparison_statistics(self, reports: List["EvaluationReport"]) -> Dict[str, Any]:
        """Bootstrap CI per report + paired significance vs the first report."""
        from agent_eval.stats import bootstrap_ci, paired_bootstrap_delta

        if len(reports) < 2:
            return {}
        labels = [r.run_id for r in reports]

        # Per-report bootstrap CI on overall score (using per-task scores as samples)
        per_report: Dict[str, Any] = {}
        all_task_scores: Dict[str, List[float]] = {}
        for r in reports:
            scores: List[float] = []
            for rows in (r.task_results or {}).values():
                for row in rows:
                    s = row.get("score")
                    if isinstance(s, (int, float)):
                        scores.append(float(s))
            all_task_scores[r.run_id] = scores
            low, high, point = bootstrap_ci(scores, seed=42)
            per_report[r.run_id] = {"mean": point, "ci_low": low, "ci_high": high, "n": len(scores)}

        # Paired significance: align rows by (evaluator, task_id) across reports,
        # take baseline = reports[0], compare each subsequent report.
        index: Dict[tuple, Dict[int, float]] = {}
        for i, r in enumerate(reports):
            for evaluator_name, rows in (r.task_results or {}).items():
                for row in rows:
                    key = (evaluator_name, row.get("task_id", ""))
                    s = row.get("score")
                    if isinstance(s, (int, float)):
                        index.setdefault(key, {})[i] = float(s)
        baseline_label = labels[0]
        baseline_scores = [index[k][0] for k in sorted(index) if 0 in index[k]]

        paired: Dict[str, Any] = {}
        for i in range(1, len(reports)):
            contender_scores = [index[k][i] for k in sorted(index) if 0 in index[k] and i in index[k]]
            delta = paired_bootstrap_delta(baseline_scores, contender_scores, seed=42)
            paired[labels[i]] = delta

        return {
            "ci": per_report,
            "paired_vs_baseline": {"baseline": baseline_label, "results": paired},
        }

    # ------------------------------------------------------------- csv export
    def export_report_csv(self, run_id: str, output_dir: str = None) -> str:
        """Export a single report's task results as CSV (flat: one row per task×evaluator)."""
        import csv
        import io

        store = self.result_store(output_dir)
        report = store.load(run_id)
        if report is None:
            raise KeyError(f"report not found: {run_id}")

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["task_id", "evaluator", "score", "passed", "response", "duration_ms"])

        task_results = report.task_results or {}
        for evaluator_name, rows in task_results.items():
            for row in rows:
                writer.writerow([
                    row.get("task_id", ""),
                    evaluator_name,
                    row.get("score", ""),
                    row.get("passed", ""),
                    (row.get("response") or "").replace("\n", "\\n") if isinstance(row.get("response"), str) else row.get("response", ""),
                    row.get("duration_ms", ""),
                ])
        return buf.getvalue()

    def export_comparison_csv(self, run_ids: List[str], output_dir: str = None) -> str:
        """Export a row-level comparison across reports as CSV."""
        import csv
        import io

        store = self.result_store(output_dir)
        row_level = store.compare_row_level(run_ids) if len(run_ids) >= 2 else {}
        if not row_level:
            raise ValueError("comparison requires at least 2 reports")

        labels = row_level.get("labels", [])
        aligned_rows = row_level.get("aligned_rows", [])
        added = row_level.get("added", [])
        removed = row_level.get("removed", [])

        buf = io.StringIO()
        writer = csv.writer(buf)

        header = ["evaluator", "task_id", "status"]
        for label in labels:
            header.append(f"score_{label}")
        for label in labels:
            header.append(f"passed_{label}")
        for label in labels[1:]:
            header.append(f"delta_{label}")
        writer.writerow(header)

        def write_row(entry: Dict[str, Any]) -> None:
            scores = entry.get("scores", {})
            passed = entry.get("passed", {})
            deltas = entry.get("score_deltas", {})
            row = [entry.get("evaluator", ""), entry.get("task_id", ""), entry.get("status", "")]
            for label in labels:
                row.append(scores.get(label, ""))
            for label in labels:
                row.append(passed.get(label, ""))
            for label in labels[1:]:
                row.append(deltas.get(label, ""))
            writer.writerow(row)

        for entry in aligned_rows:
            write_row(entry)
        for entry in added:
            write_row(entry)
        for entry in removed:
            write_row(entry)
        return buf.getvalue()

    def trend(self, agent_name: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Aggregate historical runs (optionally filtered by agent) into a trend series."""
        from agent_eval.stats import bootstrap_ci

        store = self.result_store()
        items = store.list_reports()
        if agent_name:
            items = [it for it in items if it.get("agent_name") == agent_name]
        items = sorted(items, key=lambda x: x.get("timestamp", ""))[:limit]

        points: List[Dict[str, Any]] = []
        dimension_acc: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            report = store.load(it["run_id"])
            if report is None:
                continue
            summary = report.summary or {}
            point = {
                "run_id": report.run_id,
                "timestamp": report.timestamp,
                "agent_name": report.agent_name,
                "overall_score": summary.get("overall_score"),
                "pass_rate": summary.get("pass_rate"),
                "dimensions": summary.get("dimensions", {}),
            }
            points.append(point)
            for dim, val in summary.get("dimensions", {}).items():
                dimension_acc.setdefault(dim, []).append({
                    "run_id": report.run_id,
                    "timestamp": report.timestamp,
                    "score": val,
                })

        # Compute CI bands for overall_score and pass_rate
        overall_scores = [p["overall_score"] for p in points if p.get("overall_score") is not None]
        pass_rates = [p["pass_rate"] for p in points if p.get("pass_rate") is not None]

        overall_ci = None
        if len(overall_scores) >= 2:
            low, high, mean = bootstrap_ci(overall_scores, seed=42)
            trend_dir = "up" if len(overall_scores) >= 2 and overall_scores[-1] > overall_scores[0] else "down" if overall_scores[-1] < overall_scores[0] else "flat"
            overall_ci = {"mean": mean, "ci_low": low, "ci_high": high, "n": len(overall_scores), "trend": trend_dir}

        pass_rate_ci = None
        if len(pass_rates) >= 2:
            low, high, mean = bootstrap_ci(pass_rates, seed=42)
            pass_rate_ci = {"mean": mean, "ci_low": low, "ci_high": high, "n": len(pass_rates)}

        # CI per dimension
        dimension_ci: Dict[str, Dict[str, Any]] = {}
        for dim, series in dimension_acc.items():
            scores = [s["score"] for s in series if s.get("score") is not None]
            if len(scores) >= 2:
                low, high, mean = bootstrap_ci(scores, seed=42)
                dimension_ci[dim] = {"mean": mean, "ci_low": low, "ci_high": high, "n": len(scores)}

        agents = sorted({p["agent_name"] for p in points if p.get("agent_name")})
        return {
            "agent_name": agent_name,
            "agents": agents,
            "points": points,
            "dimension_trends": dimension_acc,
            "overall_ci": overall_ci,
            "pass_rate_ci": pass_rate_ci,
            "dimension_ci": dimension_ci,
        }

    def trace_store(self) -> TraceStore:
        return TraceStore(path=self.trace_dir)

    # ----------------------------------------------------------- datasets
    def dataset_store(self):
        from agent_eval.datasets import DatasetStore
        return DatasetStore(self.workspace)

    def list_datasets(self) -> List[Dict[str, Any]]:
        return self.dataset_store().list_datasets()

    def get_dataset(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        record = self.dataset_store().get(name, version)
        return {**record.to_dict(), "versions": self.dataset_store().list_versions(name)}

    def create_dataset(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        description: str = "",
        source_traces: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self.dataset_store().create(
            name=name, rows=rows, description=description,
            source_traces=source_traces, metadata=metadata,
        )
        return record.to_dict()

    def update_dataset_rows(
        self, name: str, rows: List[Dict[str, Any]], description: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self.dataset_store().update_rows(name, rows, description)
        return record.to_dict()

    def add_dataset_version(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        description: Optional[str] = None,
        source_traces: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self.dataset_store().add_version(
            name, rows, description=description, source_traces=source_traces, metadata=metadata,
        )
        return record.to_dict()

    def delete_dataset(self, name: str) -> bool:
        return self.dataset_store().delete(name)

    def diff_dataset(self, name: str, v1: str, v2: str) -> Dict[str, Any]:
        return self.dataset_store().diff(name, v1, v2)

    def import_traces_to_dataset(
        self,
        name: str,
        trace_ids: List[str],
        description: str = "",
        create_new: bool = True,
        min_quality: float = 0.0,
    ) -> Dict[str, Any]:
        """Build dataset rows from selected traces and persist.

        ``create_new=True`` creates a new dataset; otherwise appends a new
        version to an existing one.
        """
        from agent_eval.trace.task_generator import TaskGenerator
        from agent_eval.datasets import DatasetBuilder

        store = self.trace_store()
        traces: List[TraceRecord] = []
        for tid in trace_ids:
            trace = store.load(tid)
            if trace is None:
                raise KeyError(tid)
            traces.append(trace)

        # Deduplicate via DatasetBuilder helper
        deduped = DatasetBuilder._deduplicate(traces) if traces else []
        tasks = TaskGenerator().generate_batch(deduped)
        rows: List[Dict[str, Any]] = []
        for task in tasks:
            item = task.to_dict()
            item["expected"] = item.pop("expected_output", "")
            rows.append(item)

        ds_store = self.dataset_store()
        source_trace_ids = [t.trace_id for t in deduped]
        if create_new:
            record = ds_store.create(
                name=name, rows=rows, description=description, source_traces=source_trace_ids,
            )
        else:
            record = ds_store.add_version(
                name=name, rows=rows, description=description, source_traces=source_trace_ids,
            )
        return {**record.to_dict(), "imported_count": len(rows)}

    # ------------------------------------------------------------- prompts
    def prompt_store(self):
        from agent_eval.prompts import PromptStore
        return PromptStore(self.workspace)

    def list_prompts(self) -> List[Dict[str, Any]]:
        return self.prompt_store().list_prompts()

    def get_prompt(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        record = self.prompt_store().get(name, version)
        return {**record.to_dict(), "versions": self.prompt_store().list_versions(name)}

    def create_prompt(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: str = "",
        model_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self.prompt_store().create(
            name=name, messages=messages, description=description,
            model_config=model_config, metadata=metadata,
        )
        return record.to_dict()

    def update_prompt_messages(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self.prompt_store().update_messages(name, messages, description)
        return record.to_dict()

    def add_prompt_version(
        self,
        name: str,
        messages: List[Dict[str, Any]],
        description: Optional[str] = None,
        model_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = self.prompt_store().add_version(
            name, messages, description, model_config, metadata,
        )
        return record.to_dict()

    def diff_prompt(self, name: str, v1: str, v2: str) -> Dict[str, Any]:
        return self.prompt_store().diff(name, v1, v2)

    def delete_prompt(self, name: str) -> bool:
        return self.prompt_store().delete(name)

    # ------------------------------------------------------------- reviews
    def review_store(self):
        from agent_eval.reviews import ReviewStore
        return ReviewStore(self.workspace)

    def list_reviews(self) -> List[Dict[str, Any]]:
        return self.review_store().list_sessions()

    def get_review(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        session = self.review_store().get(name, version)
        result = session.to_dict()
        result["versions"] = self.review_store().list_versions(name)
        return result

    def create_review(
        self,
        name: str,
        items: List[Dict[str, Any]],
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = self.review_store().create(
            name=name, items=items, description=description, metadata=metadata,
        )
        return session.to_dict()

    def add_review_items(self, name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        session = self.review_store().add_items(name, items)
        return session.to_dict()

    def update_review_item(
        self,
        name: str,
        item_id: str,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        labels: Optional[List[str]] = None,
        reviewer: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self.review_store().update_item(name, item_id, status, notes, labels, reviewer)
        return session.to_dict()

    def delete_review(self, name: str) -> bool:
        return self.review_store().delete(name)

    def list_traces(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = self.trace_store().query({key: value for key, value in filters.items() if value is not None})
        return [self._trace_summary(record) for record in records]

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        record = self.trace_store().load(trace_id)
        return record.to_dict() if record else None

    def score_traces(
        self,
        trace_ids: List[str],
        scorers: List[str],
    ) -> Dict[str, Any]:
        """Run scorers on selected traces and return results."""
        import time as _time

        from agent_eval.scorers.factory import ScorerFactory

        store = self.trace_store()
        results: List[Dict[str, Any]] = []
        all_scores: List[float] = []

        for tid in trace_ids:
            trace = store.load(tid)
            if trace is None:
                results.append({"trace_id": tid, "error": "trace not found", "scores": []})
                continue
            output = trace.output or ""
            input_text = trace.input or ""
            expected = trace.metadata.get("expected") or trace.metadata.get("expected_output") or ""
            score_list: List[Dict[str, Any]] = []
            for scorer_name in scorers:
                try:
                    scorer = ScorerFactory.create({"type": scorer_name})
                    t0 = _time.monotonic()
                    result = scorer.score(output, input=input_text, expected=expected)
                    elapsed = int((_time.monotonic() - t0) * 1000)
                    score_list.append({
                        **result.to_dict(),
                        "execution_time_ms": elapsed,
                    })
                    if isinstance(result.score, (int, float)):
                        all_scores.append(float(result.score))
                except Exception as exc:
                    score_list.append({
                        "name": scorer_name,
                        "score": 0.0,
                        "reason": f"scorer error: {exc}",
                        "passed": False,
                        "execution_time_ms": 0,
                    })
            results.append({
                "trace_id": tid,
                "output": output[:500],
                "scores": score_list,
            })

        summary = {
            "mean_score": sum(all_scores) / len(all_scores) if all_scores else 0.0,
            "pass_rate": sum(1 for s in all_scores if s >= 0.7) / len(all_scores) if all_scores else 0.0,
            "total": len(all_scores),
        }
        return {"results": results, "summary": summary}

    def run_playground(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        input_text: str,
        scorers: List[str],
        expected: str = "",
    ) -> Dict[str, Any]:
        """Run a single playground debug: prompt + model + scorers → output + scores."""
        import time as _time

        from agent_eval.orchestrator.agent import OpenAIAgent
        from agent_eval.scorers.factory import ScorerFactory

        # Resolve model config (api_key, base_url)
        api_key = None
        base_url = None
        try:
            cfg = EvalModelConfigStore(self.workspace).load_for_scorer()
            api_key = cfg.get("api_key") or None
            base_url = cfg.get("base_url") or None
            if not model:
                model = cfg.get("model") or "gpt-4o-mini"
        except Exception:
            model = model or "gpt-4o-mini"

        # Extract system prompt from messages
        system_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
                break

        agent = OpenAIAgent(
            model=model,
            system_prompt=system_prompt,
            temperature=0.0,
            api_key=api_key,
            base_url=base_url,
        )

        t0 = _time.monotonic()
        try:
            output = agent.generate(input_text)
        except Exception as exc:
            return {
                "output": "",
                "error": str(exc),
                "scores": [],
                "latency_ms": int((_time.monotonic() - t0) * 1000),
            }
        latency_ms = int((_time.monotonic() - t0) * 1000)

        score_list: List[Dict[str, Any]] = []
        for scorer_name in scorers:
            try:
                scorer = ScorerFactory.create({"type": scorer_name})
                result = scorer.score(output, input=input_text, expected=expected)
                score_list.append(result.to_dict())
            except Exception as exc:
                score_list.append({
                    "name": scorer_name,
                    "score": 0.0,
                    "reason": f"scorer error: {exc}",
                    "passed": False,
                })

        return {
            "output": output,
            "scores": score_list,
            "latency_ms": latency_ms,
        }

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
    def on_task_generated(evaluator, tasks):
        current = orchestrator.task_queue.progress()
        update_run(run_id, current_evaluator=evaluator.name, progress=current)

    def on_task_execute(evaluator, task):
        current = orchestrator.task_queue.progress()
        update_run(run_id, current_evaluator=evaluator.name, progress=current)

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
