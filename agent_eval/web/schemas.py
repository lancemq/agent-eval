"""API schemas for the Web UI."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConfigRequest(BaseModel):
    config: Dict[str, Any]


class ConfigValidationResponse(BaseModel):
    valid: bool
    errors: List[Dict[str, str]] = Field(default_factory=list)
    warnings: List[Dict[str, str]] = Field(default_factory=list)
    normalized: Dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    agent: Optional[str] = None
    config: Dict[str, Any]
    plugins: List[str] = Field(default_factory=list)
    output_dir: str = "./eval_results"


class RunCreateResponse(BaseModel):
    run_id: str
    status: str
    events_url: str
    status_url: str


class ReportGenerateRequest(BaseModel):
    formats: List[str] = Field(default_factory=lambda: ["json", "html", "markdown"])
    output_dir: str = "./eval_results"


class CompareReportsRequest(BaseModel):
    run_ids: List[str]
    output_dir: str = "./eval_results"


class TraceEvalConfigRequest(BaseModel):
    trace_ids: List[str]
    scorers: List[str] = Field(default_factory=list)
    eval_id: str = "trace_eval"
    name: str = "Trace-based Evaluation"
    dimensions: List[str] = Field(default_factory=lambda: ["custom"])
    threshold: float = 0.7
    aggregation: str = "weighted"


class LangfuseConfigRequest(BaseModel):
    host: str = "https://cloud.langfuse.com"
    public_key: str = ""
    secret_key: str = ""
    project: str = ""
    enabled: bool = False


class SettingsRequest(BaseModel):
    run_defaults: Dict[str, Any] = Field(default_factory=dict)
    langfuse: Dict[str, Any] = Field(default_factory=dict)
