export type ParamSpec = {
  name: string
  type: string
  default: any
  description: string
}

export type EvaluatorInfo = {
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
  num_evaluators?: number
}

export type Report = {
  run_id: string
  timestamp: string
  agent: { name: string; version: string }
  summary: ReportSummary
  evaluator_results: Record<string, any>
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
  current_evaluator?: string
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

export type DatasetRow = Record<string, any>

export type DatasetRecord = {
  name: string
  version: string
  description: string
  rows: DatasetRow[]
  created_at: string
  updated_at: string
  source_traces: string[]
  metadata: Record<string, any>
}

export type DatasetSummary = {
  name: string
  latest_version: string
  version_count: number
  row_count: number
  description: string
  updated_at: string
  created_at: string
}

export type DatasetVersionInfo = {
  version: string
  row_count: number
  created_at: string
  updated_at: string
  description: string
  source_traces: string[]
}

export type DatasetDetail = DatasetRecord & {
  versions: DatasetVersionInfo[]
}

export type DatasetDiff = {
  added: DatasetRow[]
  removed: DatasetRow[]
  modified: Array<{
    task_id: string
    fields: Record<string, { from: any; to: any }>
    before: DatasetRow
    after: DatasetRow
  }>
  summary: { added: number; removed: number; modified: number; unchanged: number }
}

export type TrendPoint = {
  run_id: string
  timestamp: string
  agent_name: string
  overall_score?: number
  pass_rate?: number
  dimensions: Record<string, number>
}

export type TrendResponse = {
  agent_name: string | null
  agents: string[]
  points: TrendPoint[]
  dimension_trends: Record<string, Array<{ run_id: string; timestamp: string; score: number }>>
  overall_ci?: { mean: number; ci_low: number; ci_high: number; n: number; trend: string }
  pass_rate_ci?: { mean: number; ci_low: number; ci_high: number; n: number }
  dimension_ci?: Record<string, { mean: number; ci_low: number; ci_high: number; n: number }>
}

export type ComparisonStatistics = {
  ci: Record<string, { mean: number; ci_low: number; ci_high: number; n: number }>
  paired_vs_baseline: {
    baseline: string
    results: Record<string, {
      mean_delta: number
      ci_low: number
      ci_high: number
      significant: boolean
      p_value_approx: number
      n: number
      positive: number
      negative: number
    }>
  }
}

export type RowLevelComparison = {
  labels: string[]
  aligned_rows: Array<{
    evaluator: string
    task_id: string
    scores: Record<string, number | null>
    passed: Record<string, boolean | null>
    responses: Record<string, any>
    score_deltas: Record<string, number>
    status: string
  }>
  added: any[]
  removed: any[]
  summary: { aligned: number; added: number; removed: number }
}

export type PromptSummary = {
  name: string
  latest_version: string
  version_count: number
  description: string
  updated_at: string
  created_at: string
}

export type PromptRecord = {
  name: string
  version: string
  description: string
  messages: Array<Record<string, any>>
  model_config: Record<string, any>
  created_at: string
  updated_at: string
  metadata: Record<string, any>
}

export type PromptVersionInfo = {
  version: string
  created_at: string
  updated_at: string
  description: string
}

export type PromptDetail = PromptRecord & {
  versions: PromptVersionInfo[]
}

export type PromptDiff = {
  added: Array<Record<string, any>>
  removed: Array<Record<string, any>>
  modified: Array<{
    index: number
    fields: Record<string, { from: any; to: any }>
    before: Record<string, any>
    after: Record<string, any>
  }>
  summary: { added: number; removed: number; modified: number; unchanged: number }
}

export type ReviewItem = {
  item_id: string
  trace_id: string
  run_id: string
  task_id: string
  output: string
  expected: string
  reviewer: string
  status: 'pending' | 'approved' | 'rejected' | 'changes_requested'
  labels: string[]
  notes: string
  created_at: string
  updated_at: string
}

export type ReviewSummary = {
  name: string
  latest_version: string
  version_count: number
  item_count: number
  pending_count: number
  description: string
  updated_at: string
  created_at: string
}

export type ReviewSession = {
  name: string
  version: string
  description: string
  items: ReviewItem[]
  created_at: string
  updated_at: string
  metadata: Record<string, any>
}

export type ReviewDetail = ReviewSession & {
  versions: Array<{ version: string; item_count: number; created_at: string; updated_at: string; description: string }>
}

export type TraceScoreResult = {
  results: Array<{
    trace_id: string
    output: string
    error?: string
    scores: Array<{
      name: string
      score: number
      reason: string
      passed: boolean
      execution_time_ms: number
    }>
  }>
  summary: { mean_score: number; pass_rate: number; total: number }
}

export type PlaygroundResult = {
  output: string
  error?: string
  scores: Array<{
    name: string
    score: number
    reason: string
    passed: boolean
    execution_time_ms: number
  }>
  latency_ms: number
}
