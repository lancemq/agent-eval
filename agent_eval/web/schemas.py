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
    evaluators: List[str] = Field(default_factory=list)
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
    eval_model: Dict[str, Any] = Field(default_factory=dict)


class DatasetCreateRequest(BaseModel):
    name: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    source_traces: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DatasetRowsUpdateRequest(BaseModel):
    rows: List[Dict[str, Any]]
    description: Optional[str] = None


class DatasetVersionRequest(BaseModel):
    rows: List[Dict[str, Any]]
    description: Optional[str] = None
    source_traces: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DatasetFromTracesRequest(BaseModel):
    trace_ids: List[str]
    description: str = ""
    create_new: bool = True
    min_quality: float = 0.0


class PromptCreateRequest(BaseModel):
    name: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    model_config_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromptMessagesUpdateRequest(BaseModel):
    messages: List[Dict[str, Any]]
    description: Optional[str] = None


class PromptVersionRequest(BaseModel):
    messages: List[Dict[str, Any]]
    description: Optional[str] = None
    model_config_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewCreateRequest(BaseModel):
    name: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewItemAddRequest(BaseModel):
    items: List[Dict[str, Any]]


class ReviewItemUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[List[str]] = None
    reviewer: Optional[str] = None


class TraceScoreRequest(BaseModel):
    trace_ids: List[str]
    scorers: List[str] = Field(default_factory=list)


class PlaygroundRunRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    model: str = ""
    input: str = ""
    scorers: List[str] = Field(default_factory=list)
    expected: str = ""
