"""FastAPI application for AgentEval Web UI."""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import agent_eval.plugins  # noqa: F401
from agent_eval import __version__
from agent_eval.config import parse_config
from agent_eval.plugins.base import PluginRegistry
from agent_eval.scorers.factory import ScorerFactory
from agent_eval.web.schemas import (
    CompareReportsRequest,
    ConfigRequest,
    ConfigValidationResponse,
    ReportGenerateRequest,
    RunCreateRequest,
    RunCreateResponse,
    LangfuseConfigRequest,
    SettingsRequest,
    TraceEvalConfigRequest,
)
from agent_eval.web.service import WebService


def create_app(output_dir: str = "./eval_results", workspace: Optional[str] = None, trace_dir: str = "./traces") -> FastAPI:
    app = FastAPI(title="AgentEval Web UI", version=__version__)
    service = WebService(output_dir=output_dir, workspace=workspace, trace_dir=trace_dir)
    app.state.service = service
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/plugins")
    def plugins():
        from agent_eval.web.metadata import get_plugin_metadata
        items = []
        for name, info in PluginRegistry.list_plugins().items():
            meta = get_plugin_metadata(name)
            items.append({"name": name, **info, **meta})
        return {"plugins": items}

    @app.get("/api/scorers")
    def scorers():
        from agent_eval.web.metadata import get_scorer_metadata
        items = []
        for name, description in ScorerFactory.list_scorers().items():
            meta = get_scorer_metadata(name)
            items.append({"type": name, "description": description, **meta})
        return {"scorers": items}

    @app.get("/api/traces")
    def traces(
        agent_name: Optional[str] = None,
        trace_type: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 0,
    ):
        return {"traces": service.list_traces({
            "agent_name": agent_name,
            "trace_type": trace_type,
            "success": success,
            "limit": limit,
        })}

    @app.get("/api/traces/{trace_id}")
    def trace_detail(trace_id: str):
        trace = service.get_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="trace not found")
        return trace

    @app.post("/api/traces/eval-config")
    def trace_eval_config(request: TraceEvalConfigRequest):
        try:
            return {"custom_eval": service.build_trace_eval_config(
                request.trace_ids,
                request.scorers,
                request.eval_id,
                request.name,
                request.dimensions,
                request.threshold,
                request.aggregation,
            )}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"trace not found: {exc.args[0]}")

    @app.get("/api/settings")
    def settings():
        return service.get_settings()

    @app.post("/api/settings")
    def save_settings(request: SettingsRequest):
        return service.save_settings(request.model_dump())

    @app.get("/api/langfuse/config")
    def langfuse_config():
        return service.get_langfuse_config()

    @app.post("/api/langfuse/config")
    def save_langfuse_config(request: LangfuseConfigRequest):
        return service.save_langfuse_config(request.model_dump())

    @app.post("/api/langfuse/test")
    def test_langfuse():
        try:
            return service.test_langfuse_connection()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/langfuse/sessions")
    def langfuse_sessions(limit: int = 50):
        try:
            return {"sessions": service.list_langfuse_sessions(limit=limit)}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/langfuse/sessions/{session_id}/traces")
    def langfuse_session_traces(session_id: str, limit: int = 50):
        try:
            return {"traces": service.list_langfuse_session_traces(session_id, limit=limit)}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/langfuse/traces/{trace_id}")
    def langfuse_trace(trace_id: str):
        try:
            return service.get_langfuse_trace(trace_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/langfuse/traces/eval-config")
    def langfuse_trace_eval_config(request: TraceEvalConfigRequest):
        try:
            return {"custom_eval": service.build_langfuse_eval_config(
                request.trace_ids,
                request.scorers,
                request.eval_id,
                request.name,
                request.dimensions,
                request.threshold,
                request.aggregation,
            )}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/config")
    def read_config(path: str = Query(...)):
        try:
            return service.read_config_file(path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/config/validate", response_model=ConfigValidationResponse)
    def validate_config(request: ConfigRequest):
        return service.validate_config(request.config)

    @app.post("/api/runs", response_model=RunCreateResponse)
    def create_run(request: RunCreateRequest):
        validation = service.validate_config(request.config)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation["errors"])
        config = parse_config(request.config)
        plugin_names = request.plugins or None
        state = service.runs.create_run(config, request.agent, plugin_names, request.output_dir)
        run_id = state["run_id"]
        return {
            "run_id": run_id,
            "status": state["status"],
            "events_url": f"/api/runs/{run_id}/events",
            "status_url": f"/api/runs/{run_id}",
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        state = service.runs.get_run(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="run not found")
        return state

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str):
        if not service.runs.get_run(run_id):
            service.event_bus.publish(run_id, "run_not_found", {"error": "run not found"})
        return EventSourceResponse(service.event_bus.stream(run_id))

    @app.get("/api/reports")
    def list_reports(output_dir: Optional[str] = None):
        return {"reports": service.result_store(output_dir).list_reports()}

    @app.get("/api/reports/{run_id}")
    def get_report(run_id: str, output_dir: Optional[str] = None):
        report = service.result_store(output_dir).load(run_id)
        if not report:
            raise HTTPException(status_code=404, detail="report not found")
        return report.to_dict()

    @app.delete("/api/reports/{run_id}")
    def delete_report(run_id: str, output_dir: Optional[str] = None):
        deleted = service.result_store(output_dir).delete(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="report not found")
        return {"deleted": True}

    @app.post("/api/reports/{run_id}/generate")
    def generate_report(run_id: str, request: ReportGenerateRequest):
        try:
            return {"generated": service.generate_report(run_id, request.formats, request.output_dir)}
        except KeyError:
            raise HTTPException(status_code=404, detail="report not found")

    @app.post("/api/reports/compare")
    def compare_reports(request: CompareReportsRequest):
        return service.compare_reports(request.run_ids, request.output_dir)

    if os.path.isdir(static_dir):
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}")
        def spa(path: str = ""):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            file_path = os.path.join(static_dir, path)
            if path and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app


app = create_app()
