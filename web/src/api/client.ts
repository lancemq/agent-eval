import type { ComparisonStatistics, DatasetDetail, DatasetDiff, DatasetRecord, DatasetSummary, LangfuseConfig, LangfuseConfigUpdate, LangfuseSession, LangfuseTrace, EvaluatorInfo, PlaygroundResult, PromptDetail, PromptDiff, PromptSummary, Report, ReportListItem, ReviewDetail, ReviewSummary, RowLevelComparison, RunState, ScorerInfo, TraceEvalConfigRequest, TraceRecord, TraceScoreResult, TraceSummary, TrendResponse, WebSettings, WebSettingsUpdate } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  const contentType = response.headers.get('content-type') || ''
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || response.statusText)
  }
  if (!contentType.includes('application/json')) {
    throw new Error(`接口 ${path} 返回了非 JSON 响应，请确认后端服务已重启并包含最新 API`)
  }
  return response.json()
}

export const api = {
  health: () => request<{ status: string; version: string }>('/api/health'),
  evaluators: async () => (await request<{ evaluators: EvaluatorInfo[] }>('/api/evaluators')).evaluators,
  scorers: async () => (await request<{ scorers: ScorerInfo[] }>('/api/scorers')).scorers,
  traces: async () => (await request<{ traces: TraceSummary[] }>('/api/traces')).traces,
  trace: (traceId: string) => request<TraceRecord>(`/api/traces/${traceId}`),
  traceEvalConfig: (payload: TraceEvalConfigRequest) => request<{ custom_eval: any }>('/api/traces/eval-config', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  settings: () => request<WebSettings>('/api/settings'),
  saveSettings: (payload: WebSettingsUpdate) => request<WebSettings>('/api/settings', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  langfuseConfig: () => request<LangfuseConfig>('/api/langfuse/config'),
  saveLangfuseConfig: (payload: LangfuseConfigUpdate) => request<LangfuseConfig>('/api/langfuse/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  testLangfuse: () => request<{ ok: boolean; host: string; sessions_checked: number }>('/api/langfuse/test', { method: 'POST' }),
  langfuseSessions: async () => (await request<{ sessions: LangfuseSession[] }>('/api/langfuse/sessions')).sessions,
  langfuseSessionTraces: async (sessionId: string) => (await request<{ traces: LangfuseTrace[] }>(`/api/langfuse/sessions/${encodeURIComponent(sessionId)}/traces`)).traces,
  langfuseTrace: (traceId: string) => request<LangfuseTrace>(`/api/langfuse/traces/${encodeURIComponent(traceId)}`),
  langfuseTraceEvalConfig: (payload: TraceEvalConfigRequest) => request<{ custom_eval: any }>('/api/langfuse/traces/eval-config', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  validateConfig: (config: any) => request<{ valid: boolean; errors: any[]; warnings: any[]; normalized: any }>('/api/config/validate', {
    method: 'POST',
    body: JSON.stringify({ config }),
  }),
  createRun: (payload: { agent?: string; config: any; evaluators: string[]; output_dir: string }) => request<{ run_id: string; status: string; events_url: string; status_url: string }>('/api/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  run: (runId: string) => request<RunState>(`/api/runs/${runId}`),
  reports: async () => (await request<{ reports: ReportListItem[] }>('/api/reports')).reports,
  report: (runId: string) => request<Report>(`/api/reports/${runId}`),
  deleteReport: (runId: string) => request<{ deleted: boolean }>(`/api/reports/${runId}`, { method: 'DELETE' }),
  compareReports: (runIds: string[]) => request<{
    reports: any[]
    comparison: any
    overall_scores: Record<string, number>
    pass_rates: Record<string, number>
    row_level: RowLevelComparison
    statistics: ComparisonStatistics
  }>('/api/reports/compare', {
    method: 'POST',
    body: JSON.stringify({ run_ids: runIds }),
  }),
  exportReportCsv: async (runId: string) => {
    const res = await fetch(`/api/reports/${runId}/export?format=csv`)
    if (!res.ok) throw new Error(await res.text())
    return res.blob()
  },
  exportComparisonCsv: async (runIds: string[]) => {
    const res = await fetch('/api/reports/compare/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_ids: runIds }),
    })
    if (!res.ok) throw new Error(await res.text())
    return res.blob()
  },
  trend: (agentName?: string, limit = 50) => request<TrendResponse>(`/api/trend${agentName ? `?agent_name=${encodeURIComponent(agentName)}` : ''}${agentName ? '&' : '?'}limit=${limit}`),
  datasets: async () => (await request<{ datasets: DatasetSummary[] }>('/api/datasets')).datasets,
  dataset: (name: string, version?: string) => request<DatasetDetail>(`/api/datasets/${encodeURIComponent(name)}${version ? `?version=${encodeURIComponent(version)}` : ''}`),
  createDataset: (payload: { name: string; rows: any[]; description?: string; source_traces?: string[] }) => request<DatasetRecord>('/api/datasets', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updateDatasetRows: (name: string, rows: any[], description?: string) => request<DatasetRecord>(`/api/datasets/${encodeURIComponent(name)}/rows`, {
    method: 'PUT',
    body: JSON.stringify({ rows, description }),
  }),
  addDatasetVersion: (name: string, payload: { rows: any[]; description?: string; source_traces?: string[] }) => request<DatasetRecord>(`/api/datasets/${encodeURIComponent(name)}/versions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  diffDataset: (name: string, v1: string, v2: string) => request<DatasetDiff>(`/api/datasets/${encodeURIComponent(name)}/diff?v1=${encodeURIComponent(v1)}&v2=${encodeURIComponent(v2)}`),
  deleteDataset: (name: string) => request<{ deleted: boolean }>(`/api/datasets/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  datasetFromTraces: (name: string, payload: { trace_ids: string[]; description?: string; create_new?: boolean }) => request<DatasetRecord & { imported_count: number }>(`/api/datasets/${encodeURIComponent(name)}/from-traces`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  prompts: async () => (await request<{ prompts: PromptSummary[] }>('/api/prompts')).prompts,
  prompt: (name: string, version?: string) => request<PromptDetail>(`/api/prompts/${encodeURIComponent(name)}${version ? `?version=${encodeURIComponent(version)}` : ''}`),
  createPrompt: (payload: { name: string; messages: any[]; description?: string; model_config_data?: Record<string, any> }) => request<PromptDetail>('/api/prompts', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updatePromptMessages: (name: string, messages: any[], description?: string) => request<PromptDetail>(`/api/prompts/${encodeURIComponent(name)}/messages`, {
    method: 'PUT',
    body: JSON.stringify({ messages, description }),
  }),
  addPromptVersion: (name: string, payload: { messages: any[]; description?: string; model_config_data?: Record<string, any> }) => request<PromptDetail>(`/api/prompts/${encodeURIComponent(name)}/versions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  diffPrompt: (name: string, v1: string, v2: string) => request<PromptDiff>(`/api/prompts/${encodeURIComponent(name)}/diff?v1=${encodeURIComponent(v1)}&v2=${encodeURIComponent(v2)}`),
  deletePrompt: (name: string) => request<{ deleted: boolean }>(`/api/prompts/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  reviews: async () => (await request<{ reviews: ReviewSummary[] }>('/api/reviews')).reviews,
  review: (name: string, version?: string) => request<ReviewDetail>(`/api/reviews/${encodeURIComponent(name)}${version ? `?version=${encodeURIComponent(version)}` : ''}`),
  createReview: (payload: { name: string; items?: any[]; description?: string }) => request<ReviewDetail>('/api/reviews', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  addReviewItems: (name: string, items: any[]) => request<ReviewDetail>(`/api/reviews/${encodeURIComponent(name)}/items`, {
    method: 'POST',
    body: JSON.stringify({ items }),
  }),
  updateReviewItem: (name: string, itemId: string, payload: { status?: string; notes?: string; labels?: string[]; reviewer?: string }) => request<ReviewDetail>(`/api/reviews/${encodeURIComponent(name)}/items/${itemId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  deleteReview: (name: string) => request<{ deleted: boolean }>(`/api/reviews/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  scoreTraces: (traceIds: string[], scorers: string[]) => request<TraceScoreResult>('/api/traces/score', {
    method: 'POST',
    body: JSON.stringify({ trace_ids: traceIds, scorers }),
  }),
  playgroundRun: (payload: { messages: any[]; model: string; input: string; scorers: string[]; expected?: string }) => request<PlaygroundResult>('/api/playground/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
}
