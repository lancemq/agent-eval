import type { LangfuseConfig, LangfuseConfigUpdate, LangfuseSession, LangfuseTrace, PluginInfo, Report, ReportListItem, RunState, ScorerInfo, TraceEvalConfigRequest, TraceRecord, TraceSummary, WebSettings, WebSettingsUpdate } from './types'

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
  plugins: async () => (await request<{ plugins: PluginInfo[] }>('/api/plugins')).plugins,
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
  createRun: (payload: { agent?: string; config: any; plugins: string[]; output_dir: string }) => request<{ run_id: string; status: string; events_url: string; status_url: string }>('/api/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  run: (runId: string) => request<RunState>(`/api/runs/${runId}`),
  reports: async () => (await request<{ reports: ReportListItem[] }>('/api/reports')).reports,
  report: (runId: string) => request<Report>(`/api/reports/${runId}`),
  deleteReport: (runId: string) => request<{ deleted: boolean }>(`/api/reports/${runId}`, { method: 'DELETE' }),
  compareReports: (runIds: string[]) => request<any>('/api/reports/compare', {
    method: 'POST',
    body: JSON.stringify({ run_ids: runIds }),
  }),
}
