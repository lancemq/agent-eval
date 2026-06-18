import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { VirtualList } from '../components/VirtualList'
import type { LangfuseConfig, LangfuseSession, LangfuseTrace, ScorerInfo, TraceRecord, TraceSummary } from '../api/types'

type Props = {
  selectedTraceIds: string[]
  setSelectedTraceIds: (ids: string[]) => void
  selectedScorers: string[]
  setSelectedScorers: (ids: string[]) => void
  setDraftEvalConfig: (config: any) => void
  setPage: (page: string) => void
}

type Tab = 'local' | 'langfuse'

const defaultLangfuseConfig: LangfuseConfig = {
  host: 'https://cloud.langfuse.com',
  public_key: '',
  project: '',
  enabled: false,
  secret_configured: false,
}

export function TraceListPage({
  selectedTraceIds,
  setSelectedTraceIds,
  selectedScorers,
  setSelectedScorers,
  setDraftEvalConfig,
  setPage,
}: Props) {
  const [tab, setTab] = useState<Tab>('local')
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [activeTrace, setActiveTrace] = useState<TraceRecord | null>(null)
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')

  const [langfuseConfig, setLangfuseConfig] = useState<LangfuseConfig>(defaultLangfuseConfig)
  const [sessions, setSessions] = useState<LangfuseSession[]>([])
  const [sessionQuery, setSessionQuery] = useState('')
  const [traceQuery, setTraceQuery] = useState('')
  const [activeSessionId, setActiveSessionId] = useState('')
  const [langfuseTraces, setLangfuseTraces] = useState<LangfuseTrace[]>([])
  const [selectedLangfuseTraceIds, setSelectedLangfuseTraceIds] = useState<string[]>([])
  const [activeLangfuseTrace, setActiveLangfuseTrace] = useState<LangfuseTrace | null>(null)
  const [loadingTraces, setLoadingTraces] = useState(false)

  useEffect(() => {
    api.traces().then(setTraces).catch((error) => setMessage(error instanceof Error ? error.message : 'Trace 加载失败'))
    api.scorers().then((items) => {
      setScorers(items)
      if (selectedScorers.length === 0) setSelectedScorers(items.slice(0, 1).map((item) => item.type))
    }).catch(console.error)
    api.langfuseConfig().then(setLangfuseConfig).catch(console.error)
  }, [])

  const filteredLocal = useMemo(
    () => traces.filter((trace) =>
      `${trace.trace_id} ${trace.agent_name} ${trace.trace_type} ${trace.tags.join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ),
    [traces, query],
  )

  const filteredSessions = useMemo(() => {
    if (!sessionQuery) return sessions
    const q = sessionQuery.toLowerCase()
    return sessions.filter((s) => {
      const id = getLangfuseId(s).toLowerCase()
      const name = String(s.name || '').toLowerCase()
      const user = String((s as any).userId || '').toLowerCase()
      return id.includes(q) || name.includes(q) || user.includes(q)
    })
  }, [sessions, sessionQuery])

  const filteredLangfuseTraces = useMemo(() => {
    if (!traceQuery) return langfuseTraces
    const q = traceQuery.toLowerCase()
    return langfuseTraces.filter((t) => {
      const id = getLangfuseId(t).toLowerCase()
      const name = String(t.name || '').toLowerCase()
      return id.includes(q) || name.includes(q)
    })
  }, [langfuseTraces, traceQuery])

  function toggleTrace(traceId: string) {
    setSelectedTraceIds(
      selectedTraceIds.includes(traceId)
        ? selectedTraceIds.filter((id) => id !== traceId)
        : [...selectedTraceIds, traceId],
    )
  }

  function toggleLangfuseTrace(traceId: string) {
    setSelectedLangfuseTraceIds(
      selectedLangfuseTraceIds.includes(traceId)
        ? selectedLangfuseTraceIds.filter((id) => id !== traceId)
        : [...selectedLangfuseTraceIds, traceId],
    )
  }

  function toggleScorer(scorer: string) {
    setSelectedScorers(
      selectedScorers.includes(scorer)
        ? selectedScorers.filter((id) => id !== scorer)
        : [...selectedScorers, scorer],
    )
  }

  async function createEval() {
    if (selectedTraceIds.length === 0) return setMessage('请至少选择一个 trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    try {
      const result = await api.traceEvalConfig({
        trace_ids: selectedTraceIds,
        scorers: selectedScorers,
        eval_id: `trace_eval_${Date.now()}`,
        name: 'Trace-based Evaluation',
        dimensions: ['trace_quality'],
        threshold: 0.7,
        aggregation: 'weighted',
      })
      setDraftEvalConfig(result.custom_eval)
      setPage('run')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '生成评测配置失败')
    }
  }

  async function testLangfuse() {
    try {
      const result = await api.testLangfuse()
      setMessage(`Langfuse 连接成功：${result.host}，检查 sessions ${result.sessions_checked} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '连接测试失败')
    }
  }

  async function loadSessions() {
    try {
      const items = await api.langfuseSessions()
      setSessions(items)
      setMessage(`已加载 ${items.length} 个 sessions`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载 sessions 失败')
    }
  }

  async function loadSessionTraces(sessionId: string) {
    setActiveSessionId(sessionId)
    setActiveLangfuseTrace(null)
    setLoadingTraces(true)
    setTraceQuery('')
    try {
      const items = await api.langfuseSessionTraces(sessionId)
      setLangfuseTraces(items)
      setSelectedLangfuseTraceIds([])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载 traces 失败')
      setLangfuseTraces([])
    } finally {
      setLoadingTraces(false)
    }
  }

  async function createLangfuseEval() {
    if (selectedLangfuseTraceIds.length === 0) return setMessage('请至少选择一个 Langfuse trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    try {
      const result = await api.langfuseTraceEvalConfig({
        trace_ids: selectedLangfuseTraceIds,
        scorers: selectedScorers,
        eval_id: `langfuse_eval_${Date.now()}`,
        name: 'Langfuse Trace Evaluation',
        dimensions: ['langfuse_quality'],
        threshold: 0.7,
        aggregation: 'weighted',
      })
      setDraftEvalConfig(result.custom_eval)
      setPage('run')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '生成评测配置失败')
    }
  }

  const langfuseConfigured = langfuseConfig.enabled && langfuseConfig.secret_configured

  return (
    <section>
      <div className="page-header">
        <h2>Trace 列表</h2>
        <div className="actions-inline">
          <button className={tab === 'local' ? 'primary' : ''} onClick={() => setTab('local')}>本地 Trace</button>
          <button className={tab === 'langfuse' ? 'primary' : ''} onClick={() => setTab('langfuse')}>Langfuse</button>
        </div>
      </div>
      <div className="cards">
        <div className="card score-card"><span>本地 Trace</span><strong>{traces.length}</strong></div>
        <div className="card score-card"><span>本地已选</span><strong>{selectedTraceIds.length}</strong></div>
        <div className="card score-card"><span>Langfuse Sessions</span><strong>{sessions.length}</strong></div>
        <div className="card score-card"><span>Scorer</span><strong>{selectedScorers.length}</strong></div>
      </div>
      {message && <p className="message">{message}</p>}

      {tab === 'local' ? (
        <div className="trace-three-pane">
          <div className="pane pane-list">
            <div className="pane-header">
              <div className="pane-header-row">
                <h3>本地 Trace <small>{filteredLocal.length}/{traces.length}</small></h3>
                <button onClick={() => setSelectedTraceIds(filteredLocal.map((t) => t.trace_id))}>全选当前</button>
              </div>
              <input
                placeholder="搜索 trace_id / agent / type / tag"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="pane-body">
              {filteredLocal.length === 0 ? (
                <EmptyPane label="暂无 Trace" hint={query ? '没有匹配的结果' : '本地 trace store 为空'} />
              ) : (
                <VirtualList
                  className="row-list row-list-virtual"
                  items={filteredLocal}
                  itemHeight={56}
                  getKey={(t) => t.trace_id}
                  renderItem={(trace) => {
                    const checked = selectedTraceIds.includes(trace.trace_id)
                    const active = activeTrace?.trace_id === trace.trace_id
                    return (
                      <div
                        className={`compact-row ${active ? 'active' : ''}`}
                        onClick={() => api.trace(trace.trace_id).then(setActiveTrace)}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => { e.stopPropagation(); toggleTrace(trace.trace_id) }}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="compact-row-main">
                          <div className="compact-row-title">
                            <code>{trace.trace_id}</code>
                            <span className="status">{trace.trace_type}</span>
                          </div>
                          <div className="compact-row-meta">
                            <span>{trace.agent_name}</span>
                            <span>·</span>
                            <span>质量 {trace.quality_score.toFixed(2)}</span>
                            <span>·</span>
                            <span>{trace.duration_ms}ms</span>
                          </div>
                        </div>
                      </div>
                    )
                  }}
                />
              )}
            </div>
            <div className="pane-footer">
              <span className="muted">已选 {selectedTraceIds.length}</span>
              <button className="primary" onClick={createEval}>生成评测配置</button>
            </div>
          </div>

          <ScorerPane scorers={scorers} selectedScorers={selectedScorers} toggleScorer={toggleScorer} />

          <div className="pane">
            <div className="pane-header"><h3>Trace 详情</h3></div>
            <div className="pane-body pane-body-padded">
              {activeTrace ? (
                <>
                  <p><strong>{activeTrace.trace_id}</strong></p>
                  <p className="muted small">{activeTrace.agent_name}</p>
                  <p className="muted">输入</p>
                  <pre className="json-preview">{activeTrace.input}</pre>
                  <p className="muted">输出</p>
                  <pre className="json-preview">{activeTrace.output}</pre>
                </>
              ) : (
                <EmptyPane label="点击列表查看详情" hint="或选中后生成评测配置" />
              )}
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="card connection-card">
            <div className="connection-meta">
              <div>
                <h3>Langfuse</h3>
                <p className="muted small">配置已迁移到配置中心。</p>
              </div>
              <div className="connection-fields">
                <div className="list-row inline-field"><span>Host</span><code>{langfuseConfig.host}</code></div>
                <div className="list-row inline-field"><span>Project</span><code>{langfuseConfig.project || '-'}</code></div>
              </div>
            </div>
            <div className="connection-actions">
              <span className={`status ${langfuseConfigured ? 'completed' : 'failed'}`}>
                {langfuseConfigured ? 'configured' : 'not configured'}
              </span>
              <button onClick={() => setPage('settings')}>配置中心</button>
              <button onClick={testLangfuse}>测试连接</button>
              <button className="primary" onClick={loadSessions}>加载 Sessions</button>
            </div>
          </div>

          <div className="trace-three-pane">
            {/* Sessions pane */}
            <div className="pane pane-list">
              <div className="pane-header">
                <div className="pane-header-row">
                  <h3>Sessions <small>{filteredSessions.length}/{sessions.length}</small></h3>
                </div>
                <input
                  placeholder="搜索 session id / name / user"
                  value={sessionQuery}
                  onChange={(e) => setSessionQuery(e.target.value)}
                />
              </div>
              <div className="pane-body">
                {sessions.length === 0 ? (
                  <EmptyPane label="尚未加载" hint="点击右上方 “加载 Sessions”" />
                ) : filteredSessions.length === 0 ? (
                  <EmptyPane label="无匹配结果" hint="尝试清空搜索词" />
                ) : (
                  <VirtualList
                    className="row-list row-list-virtual"
                    items={filteredSessions}
                    itemHeight={56}
                    getKey={(s, i) => getLangfuseId(s) || `s-${i}`}
                    renderItem={(session) => {
                      const id = getLangfuseId(session)
                      const active = activeSessionId === id
                      return (
                        <div
                          className={`compact-row ${active ? 'active' : ''}`}
                          onClick={() => loadSessionTraces(id)}
                        >
                          <div className="compact-row-main">
                            <div className="compact-row-title">
                              <code>{id}</code>
                            </div>
                            <div className="compact-row-meta">
                              <span>{session.name || (session as any).userId || '-'}</span>
                              <span>·</span>
                              <span>{session.createdAt || session.updatedAt || '-'}</span>
                            </div>
                          </div>
                        </div>
                      )
                    }}
                  />
                )}
              </div>
            </div>

            {/* Traces pane */}
            <div className="pane pane-list">
              <div className="pane-header">
                <div className="pane-header-row">
                  <h3>
                    Traces
                    {activeSessionId ? (
                      <small> · {filteredLangfuseTraces.length}/{langfuseTraces.length}</small>
                    ) : null}
                  </h3>
                  {activeSessionId && (
                    <button
                      onClick={() =>
                        setSelectedLangfuseTraceIds(filteredLangfuseTraces.map((t) => getLangfuseId(t)))
                      }
                    >
                      全选当前
                    </button>
                  )}
                </div>
                {activeSessionId && (
                  <>
                    <div className="pane-subhead">
                      <span className="muted small">Session</span>
                      <code className="ellipsis">{activeSessionId}</code>
                    </div>
                    <input
                      placeholder="搜索 trace id / name"
                      value={traceQuery}
                      onChange={(e) => setTraceQuery(e.target.value)}
                    />
                  </>
                )}
              </div>
              <div className="pane-body">
                {!activeSessionId ? (
                  <EmptyPane label="请先选择 Session" hint="左侧点击任意 session 加载其 traces" />
                ) : loadingTraces ? (
                  <EmptyPane label="加载中…" hint="" />
                ) : filteredLangfuseTraces.length === 0 ? (
                  <EmptyPane label="该 Session 暂无 trace" hint={traceQuery ? '尝试清空搜索词' : ''} />
                ) : (
                  <VirtualList
                    className="row-list row-list-virtual"
                    items={filteredLangfuseTraces}
                    itemHeight={56}
                    getKey={(t, i) => getLangfuseId(t) || `t-${i}`}
                    renderItem={(trace) => {
                      const id = getLangfuseId(trace)
                      const checked = selectedLangfuseTraceIds.includes(id)
                      const active = !!(activeLangfuseTrace && getLangfuseId(activeLangfuseTrace) === id)
                      return (
                        <div
                          className={`compact-row ${active ? 'active' : ''}`}
                          onClick={() => api.langfuseTrace(id).then(setActiveLangfuseTrace)}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => { e.stopPropagation(); toggleLangfuseTrace(id) }}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <div className="compact-row-main">
                            <div className="compact-row-title">
                              <code>{id}</code>
                            </div>
                            <div className="compact-row-meta">
                              <span>{trace.name || '-'}</span>
                              <span>·</span>
                              <span>{trace.timestamp || trace.createdAt || '-'}</span>
                            </div>
                          </div>
                        </div>
                      )
                    }}
                  />
                )}
              </div>
              <div className="pane-footer">
                <span className="muted">已选 {selectedLangfuseTraceIds.length}</span>
                <button className="primary" onClick={createLangfuseEval} disabled={selectedLangfuseTraceIds.length === 0}>
                  生成评测配置
                </button>
              </div>
            </div>

            {/* Scorer + detail pane */}
            <div className="pane pane-stack">
              <div className="pane-header"><h3>Scorer</h3></div>
              <div className="pane-body pane-body-padded option-list-pane">
                {scorers.map((scorer) => (
                  <label className="check-row" key={scorer.type}>
                    <input
                      type="checkbox"
                      checked={selectedScorers.includes(scorer.type)}
                      onChange={() => toggleScorer(scorer.type)}
                    />
                    <span>
                      <strong>{scorer.type}</strong>
                      <br />
                      <small className="muted">{scorer.description}</small>
                    </span>
                  </label>
                ))}
              </div>
              <div className="pane-divider" />
              <div className="pane-header"><h3>Trace 详情</h3></div>
              <div className="pane-body pane-body-padded">
                {activeLangfuseTrace ? (
                  <>
                    <p><strong>{getLangfuseId(activeLangfuseTrace)}</strong></p>
                    <p className="muted small">{activeLangfuseTrace.name || '-'}</p>
                    <p className="muted">输入</p>
                    <pre className="json-preview">{formatValue(activeLangfuseTrace.input)}</pre>
                    <p className="muted">输出</p>
                    <pre className="json-preview">{formatValue(activeLangfuseTrace.output)}</pre>
                  </>
                ) : (
                  <EmptyPane label="未选 Trace" hint="点击中间列表查看详情" />
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

function ScorerPane({
  scorers,
  selectedScorers,
  toggleScorer,
}: {
  scorers: ScorerInfo[]
  selectedScorers: string[]
  toggleScorer: (scorer: string) => void
}) {
  return (
    <div className="pane">
      <div className="pane-header"><h3>Scorer <small>{selectedScorers.length}/{scorers.length}</small></h3></div>
      <div className="pane-body pane-body-padded option-list-pane">
        {scorers.map((scorer) => (
          <label className="check-row" key={scorer.type}>
            <input
              type="checkbox"
              checked={selectedScorers.includes(scorer.type)}
              onChange={() => toggleScorer(scorer.type)}
            />
            <span>
              <strong>{scorer.type}</strong>
              <br />
              <small className="muted">{scorer.description}</small>
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}

function EmptyPane({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="empty-pane">
      <strong>{label}</strong>
      {hint ? <small className="muted">{hint}</small> : null}
    </div>
  )
}

function getLangfuseId(item: LangfuseSession | LangfuseTrace): string {
  return String((item as any).id || (item as any).sessionId || (item as any).trace_id || '')
}

function formatValue(value: any): string {
  if (value === undefined || value === null) return ''
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}
