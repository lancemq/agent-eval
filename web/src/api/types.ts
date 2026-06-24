export type ParamSpec = {
  name: string
  type: string
  default: any
  description: string
}

export type PluginInfo = {
  name: string
  version: string
  type: string
  dimensions: string[]
  description: string
  params?: ParamSpec[]
  use_cases?: string[]
  example?: Record<string, any>
}

export type ScorerInfo = {
  type: string
  description: string
  params?: ParamSpec[]
  requires?: string[]
  dimensions?: string[]
  use_cases?: string[]
  example?: Record<string, any>
}

export type ReportSummary = {
  overall_score?: number
  macro_score?: number
  micro_score?: number
  total_tasks?: number
  total_passed?: number
  total_failed?: number
  pass_rate?: number
  dimensions?: Record<string, number>
  num_plugins?: number
}

export type Report = {
  run_id: string
  timestamp: string
  agent: { name: string; version: string }
  summary: ReportSummary
  plugin_results: Record<string, any>
  task_results: Record<string, any[]>
  metadata: Record<string, any>
  artifacts_count: number
}

export type ReportListItem = {
  run_id: string
  timestamp: string
  agent_name: string
  overall_score?: number
}

export type RunState = {
  run_id: string
  status: string
  created_at: string
  started_at?: string
  completed_at?: string
  progress: { total: number; pending: number; running: number; completed: number; failed: number }
  current_plugin?: string
  summary?: ReportSummary
  error?: string
  report_id?: string
  generated_reports: Record<string, string>
}

export type RunEvent = {
  type: string
  run_id: string
  timestamp: string
  [key: string]: any
}

export type TraceSummary = {
  trace_id: string
  timestamp: string
  agent_name: string
  trace_type: string
  success: boolean
  quality_score: number
  duration_ms: number
  tags: string[]
  num_tool_calls: number
  num_turns: number
}

export type TraceRecord = TraceSummary & {
  agent_version: string
  input: string
  messages: Array<Record<string, string>>
  trajectory: any[]
  output: string
  output_structured?: Record<string, any>
  tool_calls: any[]
  metadata: Record<string, any>
  error?: string
  source: string
  raw?: Record<string, any>
}

export type TraceEvalConfigRequest = {
  trace_ids: string[]
  scorers: string[]
  eval_id: string
  name: string
  dimensions: string[]
  threshold?: number
  aggregation?: string
}

export type LangfuseConfig = {
  host: string
  public_key: string
  project: string
  enabled: boolean
  secret_configured: boolean
}

export type LangfuseConfigUpdate = {
  host: string
  public_key: string
  secret_key: string
  project: string
  enabled: boolean
}

export type LangfuseSession = {
  id?: string
  sessionId?: string
  name?: string
  userId?: string
  createdAt?: string
  updatedAt?: string
  [key: string]: any
}

export type LangfuseTrace = {
  id?: string
  trace_id?: string
  name?: string
  sessionId?: string
  input?: any
  output?: any
  timestamp?: string
  createdAt?: string
  [key: string]: any
}

export type RunDefaults = {
  agent: string
  output_dir: string
  report_formats: string[]
  orchestrator: {
    max_workers: number
    queue_backend: string
    storage: { type: string; output_dir: string }
    log_level: string
  }
}

export type EvalModelConfig = {
  model: string
  base_url: string
  timeout: number
  api_key_configured: boolean
}

export type EvalModelConfigUpdate = {
  model: string
  api_key: string
  base_url: string
  timeout: number
}

export type WebSettings = {
  run_defaults: RunDefaults
  trace: { trace_dir: string }
  langfuse: LangfuseConfig
  eval_model: EvalModelConfig
}

export type WebSettingsUpdate = {
  run_defaults: RunDefaults
  langfuse: LangfuseConfigUpdate
  eval_model: EvalModelConfigUpdate
}
