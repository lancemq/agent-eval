"""Experiment tracking integration (MLflow / Weights & Biases).

Automatically logs evaluation metrics, parameters, and artifacts
to MLflow or W&B when available.

Usage:
    from agent_eval.tracking import TrackingBackend, track_run

    # Auto-detect available backend (MLflow > W&B)
    backend = TrackingBackend.create("auto")
    backend.log_report(report)

    # Or specify explicitly
    mlflow_backend = TrackingBackend.create("mlflow", experiment="my-evals")
    wb_backend = TrackingBackend.create("wandb", project="agent-eval")
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from agent_eval.orchestrator.result_store import EvaluationReport

logger = logging.getLogger("agent_eval.tracking")


class BaseTracker(ABC):
    """Abstract interface for experiment tracking backends."""

    @abstractmethod
    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Start a new tracking run. Returns run ID."""
        ...

    @abstractmethod
    def log_metrics(self, metrics: Dict[str, float], step: int = 0) -> None:
        """Log numeric metrics."""
        ...

    @abstractmethod
    def log_params(self, params: Dict[str, Any]) -> None:
        """Log run parameters."""
        ...

    @abstractmethod
    def log_artifact(self, path: str) -> None:
        """Log a file artifact (e.g., JSON report)."""
        ...

    @abstractmethod
    def end_run(self) -> None:
        """End the current run."""
        ...

    def log_report(self, report: EvaluationReport) -> None:
        """Log an evaluation report (default implementation)."""
        self.log_params({
            "agent_name": report.agent_name,
            "agent_version": report.agent_version,
            "run_id": report.run_id,
        })
        self.log_metrics({
            "overall_score": report.summary.get("overall_score", 0),
            "macro_score": report.summary.get("macro_score", 0),
            "micro_score": report.summary.get("micro_score", 0),
            "pass_rate": report.summary.get("pass_rate", 0),
            "total_tasks": float(report.summary.get("total_tasks", 0)),
            "total_passed": float(report.summary.get("total_passed", 0)),
        })
        for dim, score in report.summary.get("dimensions", {}).items():
            self.log_metrics({f"dim_{dim}": score})
        for pname, pstats in report.plugin_results.items():
            self.log_metrics({
                f"plugin_{pname}_score": pstats.get("score", 0),
                f"plugin_{pname}_pass_rate": pstats.get("pass_rate", 0),
            })


class MLflowTracker(BaseTracker):
    """MLflow experiment tracking backend."""

    def __init__(
        self,
        experiment: str = "agent_eval",
        tracking_uri: Optional[str] = None,
    ):
        try:
            import mlflow
        except ImportError as e:
            raise RuntimeError("mlflow not installed: pip install mlflow") from e
        self._mlflow = mlflow
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        self._run_id: Optional[str] = None

    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> str:
        run = self._mlflow.start_run(run_name=run_name, tags=tags or {})
        self._run_id = run.info.run_id
        return self._run_id

    def log_metrics(self, metrics: Dict[str, float], step: int = 0) -> None:
        self._mlflow.log_metrics(metrics, step=step)

    def log_params(self, params: Dict[str, Any]) -> None:
        self._mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_artifact(self, path: str) -> None:
        self._mlflow.log_artifact(path)

    def end_run(self) -> None:
        self._mlflow.end_run()
        self._run_id = None


class WandbTracker(BaseTracker):
    """Weights & Biases tracking backend."""

    def __init__(
        self,
        project: str = "agent-eval",
        entity: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        try:
            import wandb
        except ImportError as e:
            raise RuntimeError("wandb not installed: pip install wandb") from e
        self._wandb = wandb
        self._project = project
        self._entity = entity
        self._api_key = api_key
        self._run: Any = None

    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> str:
        self._run = self._wandb.init(
            project=self._project,
            entity=self._entity,
            name=run_name,
            tags=list((tags or {}).keys()),
        )
        return self._run.id if self._run else ""

    def log_metrics(self, metrics: Dict[str, float], step: int = 0) -> None:
        if self._run:
            self._wandb.log(metrics, step=step)

    def log_params(self, params: Dict[str, Any]) -> None:
        if self._run:
            self._wandb.config.update(params)

    def log_artifact(self, path: str) -> None:
        if self._run:
            artifact = self._wandb.Artifact(name=path.split("/")[-1], type="file")
            artifact.add_file(path)
            self._wandb.log_artifact(artifact)

    def end_run(self) -> None:
        if self._run:
            self._wandb.finish()
            self._run = None


class NoopTracker(BaseTracker):
    """No-op tracker for when no backend is available."""

    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> str:
        return ""

    def log_metrics(self, metrics: Dict[str, float], step: int = 0) -> None:
        pass

    def log_params(self, params: Dict[str, Any]) -> None:
        pass

    def log_artifact(self, path: str) -> None:
        pass

    def end_run(self) -> None:
        pass


class TrackingBackend:
    """Factory for creating tracking backends."""

    @staticmethod
    def create(
        backend: str = "auto",
        **kwargs: Any,
    ) -> BaseTracker:
        """Create a tracking backend.

        Args:
            backend: "mlflow", "wandb", "auto" (try MLflow → W&B → Noop), or "none"
            **kwargs: Backend-specific config (experiment, project, etc.)
        """
        backend = backend.lower().strip()

        if backend == "none":
            return NoopTracker()

        if backend == "mlflow":
            return MLflowTracker(**kwargs)

        if backend == "wandb" or backend == "w&b" or backend == "weights_biases":
            return WandbTracker(**kwargs)

        if backend == "auto":
            # Try MLflow first, then W&B, then Noop
            try:
                return MLflowTracker(**{
                    k: v for k, v in kwargs.items()
                    if k in ("experiment", "tracking_uri")
                })
            except (ImportError, RuntimeError):
                pass
            try:
                return WandbTracker(**{
                    k: v for k, v in kwargs.items()
                    if k in ("project", "entity", "api_key")
                })
            except (ImportError, RuntimeError):
                pass
            logger.info("No tracking backend available, using NoopTracker")
            return NoopTracker()

        raise ValueError(f"Unknown tracking backend: '{backend}'. Use 'mlflow', 'wandb', 'auto', or 'none'.")


def track_run(
    report: EvaluationReport,
    backend: str = "auto",
    **kwargs: Any,
) -> Optional[str]:
    """One-shot helper: log a report to a tracking backend.

    Args:
        report: Evaluation report to log
        backend: Tracking backend name
        **kwargs: Backend config

    Returns:
        Run ID if tracking succeeded, None otherwise.
    """
    tracker = TrackingBackend.create(backend, **kwargs)
    if isinstance(tracker, NoopTracker):
        return None

    try:
        run_id = tracker.start_run(
            run_name=f"{report.agent_name}-{report.run_id[:8]}",
            tags={"agent": report.agent_name, "version": report.agent_version},
        )
        tracker.log_report(report)
        tracker.end_run()
        logger.info(f"Logged run {run_id} to {backend}")
        return run_id
    except Exception as e:
        logger.warning(f"Failed to track run: {e}")
        try:
            tracker.end_run()
        except Exception:
            pass
        return None
