"""FastAPI application for AgentEval Web UI."""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import agent_eval.evaluators  # noqa: F401
from agent_eval import __version__
from agent_eval.config import parse_config
from agent_eval.evaluators.base import EvaluatorRegistry
from agent_eval.scorers.factory import ScorerFactory
from agent_eval.web.schemas import (
    CompareReportsRequest,
    ConfigRequest,
    ConfigValidationResponse,
    DatasetCreateRequest,
    DatasetFromTracesRequest,
    DatasetRowsUpdateRequest,
    DatasetVersionRequest,
    PromptCreateRequest,
    PromptMessagesUpdateRequest,
    PromptVersionRequest,
    ReportGenerateRequest,
    ReviewCreateRequest,
    ReviewItemAddRequest,
    ReviewItemUpdateRequest,
    RunCreateRequest,
    RunCreateResponse,
    LangfuseConfigRequest,
    SettingsRequest,
    TraceEvalConfigRequest,
    TraceScoreRequest,
    PlaygroundRunRequest,
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

    @app.get("/api/evaluators")
    def evaluators():
        from agent_eval.web.metadata import get_evaluator_metadata
        items = []
        for name, info in EvaluatorRegistry.list_evaluators().items():
            meta = get_evaluator_metadata(name)
            items.append({"name": name, **info, **meta})
        return {"evaluators": items}

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

    @app.post("/api/traces/score")
    def score_traces(request: TraceScoreRequest):
        if not request.trace_ids:
            raise HTTPException(status_code=400, detail="trace_ids is required")
        if not request.scorers:
            raise HTTPException(status_code=400, detail="scorers is required")
        return service.score_traces(request.trace_ids, request.scorers)

    @app.post("/api/playground/run")
    def playground_run(request: PlaygroundRunRequest):
        if not request.input:
            raise HTTPException(status_code=400, detail="input is required")
        return service.run_playground(
            messages=request.messages,
            model=request.model,
            input_text=request.input,
            scorers=request.scorers,
            expected=request.expected,
        )

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
        evaluator_names = request.evaluators or None
        state = service.runs.create_run(config, request.agent, evaluator_names, request.output_dir)
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

    @app.get("/api/reports/{run_id}/export")
    def export_report(run_id: str, format: str = Query("csv"), output_dir: Optional[str] = None):
        if format != "csv":
            raise HTTPException(status_code=400, detail="only csv format supported")
        try:
            csv_text = service.export_report_csv(run_id, output_dir)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
        )

    @app.post("/api/reports/compare/export")
    def export_comparison(request: CompareReportsRequest):
        try:
            csv_text = service.export_comparison_csv(request.run_ids, request.output_dir)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        filename = "comparison_" + "_".join(request.run_ids[:3]) + ".csv"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/trend")
    def trend(agent_name: Optional[str] = Query(None), limit: int = Query(50)):
        return service.trend(agent_name=agent_name, limit=limit)

    # ----------------------------------------------------------- datasets
    @app.get("/api/datasets")
    def list_datasets():
        return {"datasets": service.list_datasets()}

    @app.get("/api/datasets/{name}")
    def get_dataset(name: str, version: Optional[str] = Query(None)):
        try:
            return service.get_dataset(name, version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/datasets")
    def create_dataset(request: DatasetCreateRequest):
        try:
            return service.create_dataset(
                name=request.name, rows=request.rows, description=request.description,
                source_traces=request.source_traces, metadata=request.metadata,
            )
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.put("/api/datasets/{name}/rows")
    def update_dataset_rows(name: str, request: DatasetRowsUpdateRequest):
        try:
            return service.update_dataset_rows(name, request.rows, request.description)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/datasets/{name}/versions")
    def add_dataset_version(name: str, request: DatasetVersionRequest):
        try:
            return service.add_dataset_version(
                name, request.rows, description=request.description,
                source_traces=request.source_traces, metadata=request.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/api/datasets/{name}/diff")
    def diff_dataset(name: str, v1: str = Query(...), v2: str = Query(...)):
        try:
            return service.diff_dataset(name, v1, v2)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.delete("/api/datasets/{name}")
    def delete_dataset(name: str):
        deleted = service.delete_dataset(name)
        if not deleted:
            raise HTTPException(status_code=404, detail="dataset not found")
        return {"deleted": True}

    @app.post("/api/datasets/{name}/from-traces")
    def dataset_from_traces(name: str, request: DatasetFromTracesRequest):
        try:
            return service.import_traces_to_dataset(
                name=name, trace_ids=request.trace_ids, description=request.description,
                create_new=request.create_new, min_quality=request.min_quality,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"trace not found: {exc}")
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # --------------------------------------------------------------- prompts
    @app.get("/api/prompts")
    def list_prompts():
        return {"prompts": service.list_prompts()}

    @app.get("/api/prompts/{name}")
    def get_prompt(name: str, version: Optional[str] = Query(None)):
        try:
            return service.get_prompt(name, version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/prompts")
    def create_prompt(request: PromptCreateRequest):
        try:
            return service.create_prompt(
                name=request.name, messages=request.messages,
                description=request.description,
                model_config=request.model_config_data,
                metadata=request.metadata,
            )
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.put("/api/prompts/{name}/messages")
    def update_prompt_messages(name: str, request: PromptMessagesUpdateRequest):
        try:
            return service.update_prompt_messages(name, request.messages, request.description)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/prompts/{name}/versions")
    def add_prompt_version(name: str, request: PromptVersionRequest):
        try:
            return service.add_prompt_version(
                name, request.messages, request.description,
                request.model_config_data, request.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/api/prompts/{name}/diff")
    def diff_prompt(name: str, v1: str = Query(...), v2: str = Query(...)):
        try:
            return service.diff_prompt(name, v1, v2)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.delete("/api/prompts/{name}")
    def delete_prompt(name: str):
        deleted = service.delete_prompt(name)
        if not deleted:
            raise HTTPException(status_code=404, detail="prompt not found")
        return {"deleted": True}

    # --------------------------------------------------------------- reviews
    @app.get("/api/reviews")
    def list_reviews():
        return {"reviews": service.list_reviews()}

    @app.get("/api/reviews/{name}")
    def get_review(name: str, version: Optional[str] = Query(None)):
        try:
            return service.get_review(name, version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/reviews")
    def create_review(request: ReviewCreateRequest):
        try:
            return service.create_review(
                name=request.name, items=request.items,
                description=request.description, metadata=request.metadata,
            )
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/reviews/{name}/items")
    def add_review_items(name: str, request: ReviewItemAddRequest):
        try:
            return service.add_review_items(name, request.items)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.put("/api/reviews/{name}/items/{item_id}")
    def update_review_item(name: str, item_id: str, request: ReviewItemUpdateRequest):
        try:
            return service.update_review_item(
                name, item_id, request.status, request.notes,
                request.labels, request.reviewer,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/reviews/{name}")
    def delete_review(name: str):
        deleted = service.delete_review(name)
        if not deleted:
            raise HTTPException(status_code=404, detail="review not found")
        return {"deleted": True}

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
