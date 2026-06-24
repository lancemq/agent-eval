import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { VirtualList } from '../components/VirtualList'
import { useAppStore } from '../stores/appStore'
import type { LangfuseConfig, LangfuseSession, LangfuseTrace, ParamSpec, PluginInfo, ScorerInfo, TraceRecord, TraceSummary } from '../api/types'

type SubTab = 'trace' | 'scorer' | 'plugin'

const defaultLangfuseConfig: LangfuseConfig = {
  host: 'https://cloud.langfuse.com',
  public_key: '',
  project: '',
  enabled: false,
  secret_configured: false,
}

export function LibraryPage() {
  const { tab: urlTab } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState<SubTab>((urlTab as SubTab) || 'trace')

  useEffect(() => {
    if (urlTab && ['trace', 'scorer', 'plugin'].includes(urlTab)) setTab(urlTab as SubTab)
  }, [urlTab])

  return (
    <section>
      <div className="page-header">
        <h2>资源库</h2>
      </div>
      <div className="tab-bar">
        <button className={tab === 'trace' ? 'tab active' : 'tab'} onClick={() => { setTab('trace'); navigate('/library/trace') }}>Trace</button>
        <button className={tab === 'scorer' ? 'tab active' : 'tab'} onClick={() => { setTab('scorer'); navigate('/library/scorer') }}>Scorer</button>
        <button className={tab === 'plugin' ? 'tab active' : 'tab'} onClick={() => { setTab('plugin'); navigate('/library/plugin') }}>插件</button>
      </div>
      {tab === 'trace' && <TraceSection />}
      {tab === 'scorer' && <ScorerSection />}
      {tab === 'plugin' && <PluginSection />}
    </section>
  )
}

/* ───── Trace ───── */

type TraceSource = 'local' | 'langfuse'

function TraceSection() {
  const navigate = useNavigate()
  const [subTab, setSubTab] = useState<TraceSource>('local')
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [activeTrace, setActiveTrace] = useState<TraceRecord | null>(null)
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')

  const selectedTraceIds = useAppStore((s) => s.selectedTraceIds)
  const setSelectedTraceIds = useAppStore((s) => s.setSelectedTraceIds)
  const toggleTrace = useAppStore((s) => s.toggleTrace)
  const selectedScorers = useAppStore((s) => s.selectedScorers)
  const toggleScorer = useAppStore((s) => s.toggleScorer)
  const setSelectedScorers = useAppStore((s) => s.setSelectedScorers)

  // Langfuse state
  const [langfuseConfig, setLangfuseConfig] = useState<LangfuseConfig>(defaultLangfuseConfig)
  const [sessions, setSessions] = useState<LangfuseSession[]>([])
  const [sessionQuery, setSessionQuery] = useState('')
  const [activeSessionId, setActiveSessionId] = useState('')
  const [langfuseTraces, setLangfuseTraces] = useState<LangfuseTrace[]>([])
  const [selectedLangfuseTraceIds, setSelectedLangfuseTraceIds] = useState<string[]>([])
  const [activeLangfuseTrace, setActiveLangfuseTrace] = useState<LangfuseTrace | null>(null)
  const [loadingTraces, setLoadingTraces] = useState(false)
  const [traceQuery, setTraceQuery] = useState('')

  useEffect(() => {
    api.traces().then(setTraces).catch((error) => setMessage(error instanceof Error ? error.message : 'Trace 加载失败'))
    api.scorers().then((items) => {
      setScorers(items)
      if (selectedScorers.length === 0) setSelectedScorers(items.slice(0, 1).map((item) => item.type))
    }).catch(console.error)
    api.langfuseConfig().then(setLangfuseConfig).catch(console.error)
  }, [])

  const filteredLocal = useMemo(
    () => traces.filter((t) =>
      `${t.trace_id} ${t.agent_name} ${t.trace_type} ${t.tags.join(' ')}`
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

  function toggleLangfuseTrace(traceId: string) {
    setSelectedLangfuseTraceIds(
      selectedLangfuseTraceIds.includes(traceId)
        ? selectedLangfuseTraceIds.filter((id) => id !== traceId)
        : [...selectedLangfuseTraceIds, traceId],
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
      useAppStore.getState().setDraftEvalConfig(result.custom_eval)
      navigate('/run')
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
      useAppStore.getState().setDraftEvalConfig(result.custom_eval)
      navigate('/run')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '生成评测配置失败')
    }
  }

  const langfuseConfigured = langfuseConfig.enabled && langfuseConfig.secret_configured
  const allLangfuseTraceIds = filteredLangfuseTraces.map((t) => getLangfuseId(t))

  return (
    <>
      <div className="sub-tab-bar">
        <button className={subTab === 'local' ? 'primary' : ''} onClick={() => setSubTab('local')}>本地 Trace</button>
        <button className={subTab === 'langfuse' ? 'primary' : ''} onClick={() => setSubTab('langfuse')}>Langfuse</button>
      </div>
      {message && <p className="message">{message}</p>}

      {subTab === 'local' ? (
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
                      <div className={`compact-row ${active ? 'active' : ''}`} onClick={() => api.trace(trace.trace_id).then(setActiveTrace)}>
                        <input type="checkbox" checked={checked} onChange={(e) => { e.stopPropagation(); toggleTrace(trace.trace_id) }} onClick={(e) => e.stopPropagation()} />
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
              <button className="primary" onClick={createEval}>生成评测配置 →</button>
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
                <EmptyPane label="点击列表查看详情" />
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
              <button onClick={() => navigate('/settings')}>配置中心</button>
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
                  <EmptyPane label="尚未加载" hint="点击右上方「加载 Sessions」" />
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
                        <div className={`compact-row ${active ? 'active' : ''}`} onClick={() => loadSessionTraces(id)}>
                          <div className="compact-row-main">
                            <div className="compact-row-title"><code>{id}</code></div>
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
                    {activeSessionId ? <small> · {filteredLangfuseTraces.length}/{langfuseTraces.length}</small> : null}
                  </h3>
                  {activeSessionId && (
                    <button onClick={() => setSelectedLangfuseTraceIds(allLangfuseTraceIds)}>全选当前</button>
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
                  <EmptyPane label="加载中…" />
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
                            <div className="compact-row-title"><code>{id}</code></div>
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
                  生成评测配置 →
                </button>
              </div>
            </div>

            {/* Scorer + detail pane */}
            <div className="pane pane-stack">
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
    </>
  )
}

/* ───── Scorer Pane ───── */

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

/* ───── Scorer ───── */

function ScorerSection() {
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [query, setQuery] = useState('')
  const [activeType, setActiveType] = useState<string | null>(null)
  const selectedScorers = useAppStore((s) => s.selectedScorers)
  const toggleScorer = useAppStore((s) => s.toggleScorer)

  useEffect(() => { api.scorers().then(setScorers).catch(console.error) }, [])

  const filtered = useMemo(
    () => scorers.filter((s) =>
      `${s.type} ${s.description} ${(s.dimensions || []).join(' ')} ${(s.use_cases || []).join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ),
    [scorers, query],
  )

  const active = useMemo(() => scorers.find((s) => s.type === activeType) || null, [scorers, activeType])

  return (
    <div className="library-detail-layout">
      <div className="pane pane-list">
        <div className="pane-header">
          <div className="pane-header-row">
            <h3>Scorer <small>{filtered.length}/{scorers.length}</small></h3>
            <span className="muted small">已选 {selectedScorers.length}</span>
          </div>
          <input placeholder="搜索 scorer / 用途 / 维度" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="pane-body">
          {filtered.length === 0 ? (
            <EmptyPane label="无匹配" hint="尝试清空搜索词" />
          ) : (
            <VirtualList
              className="row-list row-list-virtual"
              items={filtered}
              itemHeight={68}
              getKey={(s) => s.type}
              renderItem={(s) => {
                const checked = selectedScorers.includes(s.type)
                const isActive = activeType === s.type
                return (
                  <div className={`compact-row ${isActive ? 'active' : ''}`} onClick={() => setActiveType(s.type)}>
                    <input type="checkbox" checked={checked} onChange={(e) => { e.stopPropagation(); toggleScorer(s.type) }} onClick={(e) => e.stopPropagation()} />
                    <div className="compact-row-main">
                      <div className="compact-row-title">
                        <code>{s.type}</code>
                        {(s.requires || []).slice(0, 2).map((req) => (
                          <span key={req} className="tag-pill">{req}</span>
                        ))}
                      </div>
                      <div className="compact-row-meta">
                        <span>{s.description}</span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
          )}
        </div>
      </div>

      <DetailPanel
        title={active?.type}
        description={active?.description}
        params={active?.params || []}
        requires={active?.requires || []}
        dimensions={active?.dimensions || []}
        useCases={active?.use_cases || []}
        example={active?.example}
        emptyHint="点击左侧条目查看 scorer 详细参数和示例"
      />
    </div>
  )
}

/* ───── Plugin ───── */

function PluginSection() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [query, setQuery] = useState('')
  const [activeName, setActiveName] = useState<string | null>(null)

  useEffect(() => { api.plugins().then(setPlugins).catch(console.error) }, [])

  const filtered = useMemo(
    () => plugins.filter((p) =>
      `${p.name} ${p.type} ${p.description} ${p.dimensions.join(' ')} ${(p.use_cases || []).join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ),
    [plugins, query],
  )

  const active = useMemo(() => plugins.find((p) => p.name === activeName) || null, [plugins, activeName])

  return (
    <div className="library-detail-layout">
      <div className="pane pane-list">
        <div className="pane-header">
          <div className="pane-header-row">
            <h3>插件 <small>{filtered.length}/{plugins.length}</small></h3>
          </div>
          <input placeholder="搜索 plugin / 类型 / 维度 / 场景" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <div className="pane-body">
          {filtered.length === 0 ? (
            <EmptyPane label="无匹配" hint="尝试清空搜索词" />
          ) : (
            <VirtualList
              className="row-list row-list-virtual"
              items={filtered}
              itemHeight={68}
              getKey={(p) => p.name}
              renderItem={(p) => {
                const isActive = activeName === p.name
                return (
                  <div className={`compact-row ${isActive ? 'active' : ''}`} onClick={() => setActiveName(p.name)}>
                    <div className="compact-row-main">
                      <div className="compact-row-title">
                        <code>{p.name}</code>
                        <span className="tag-pill">{p.type}</span>
                      </div>
                      <div className="compact-row-meta">
                        <span>{p.description || '无描述'}</span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
          )}
        </div>
      </div>

      <DetailPanel
        title={active?.name}
        subtitle={active ? `${active.type} · v${active.version}` : undefined}
        description={active?.description}
        params={active?.params || []}
        dimensions={active?.dimensions || []}
        useCases={active?.use_cases || []}
        example={active?.example}
        emptyHint="点击左侧条目查看插件详细参数和示例"
      />
    </div>
  )
}

/* ───── Detail Panel (shared by scorer & plugin) ───── */

function DetailPanel({
  title,
  subtitle,
  description,
  params,
  requires,
  dimensions,
  useCases,
  example,
  emptyHint,
}: {
  title?: string
  subtitle?: string
  description?: string
  params: ParamSpec[]
  requires?: string[]
  dimensions?: string[]
  useCases?: string[]
  example?: Record<string, any>
  emptyHint: string
}) {
  const [copied, setCopied] = useState(false)
  const yamlSnippet = useMemo(() => (example ? toYaml(example) : ''), [example])

  function copy() {
    if (!yamlSnippet) return
    navigator.clipboard?.writeText(yamlSnippet).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }

  if (!title) {
    return (
      <div className="pane">
        <div className="pane-header"><h3>详情</h3></div>
        <div className="pane-body pane-body-padded">
          <EmptyPane label="未选择" hint={emptyHint} />
        </div>
      </div>
    )
  }

  return (
    <div className="pane">
      <div className="pane-header">
        <h3>
          <code>{title}</code>
          {subtitle && <small className="muted" style={{ marginLeft: 8 }}>{subtitle}</small>}
        </h3>
      </div>
      <div className="pane-body pane-body-padded detail-body">
        {description && <p>{description}</p>}

        {requires && requires.length > 0 && (
          <section className="detail-section">
            <h4>依赖与前置条件</h4>
            <div className="tags">{requires.map((req) => <span key={req}>{req}</span>)}</div>
          </section>
        )}

        {dimensions && dimensions.length > 0 && (
          <section className="detail-section">
            <h4>评测维度</h4>
            <div className="tags">{dimensions.map((dim) => <span key={dim}>{dim}</span>)}</div>
          </section>
        )}

        {useCases && useCases.length > 0 && (
          <section className="detail-section">
            <h4>适用场景</h4>
            <ul className="bullet-list">{useCases.map((uc) => <li key={uc}>{uc}</li>)}</ul>
          </section>
        )}

        <section className="detail-section">
          <h4>参数</h4>
          {params.length === 0 ? (
            <p className="muted small">该项无可配置参数</p>
          ) : (
            <table className="param-table">
              <thead><tr><th>名称</th><th>类型</th><th>默认值</th><th>说明</th></tr></thead>
              <tbody>
                {params.map((p) => (
                  <tr key={p.name}>
                    <td><code>{p.name}</code></td>
                    <td><small>{p.type}</small></td>
                    <td><code className="small">{formatDefault(p.default)}</code></td>
                    <td>{p.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {yamlSnippet && (
          <section className="detail-section">
            <div className="section-title">
              <h4>示例 YAML</h4>
              <button onClick={copy}>{copied ? '已复制 ✓' : '复制'}</button>
            </div>
            <pre className="json-preview">{yamlSnippet}</pre>
          </section>
        )}
      </div>
    </div>
  )
}

function formatDefault(value: any): string {
  if (value === undefined || value === null) return '—'
  if (typeof value === 'string') return value === '' ? '""' : value
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function toYaml(obj: any, indent = 0): string {
  const pad = '  '.repeat(indent)
  if (obj === null || obj === undefined) return 'null'
  if (typeof obj === 'string') return obj
  if (typeof obj === 'number' || typeof obj === 'boolean') return String(obj)
  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]'
    return obj.map((item) => {
      if (typeof item === 'object' && item !== null) {
        const inner = toYaml(item, indent + 1)
        return `${pad}- ${inner.trimStart()}`
      }
      return `${pad}- ${toYaml(item, indent + 1)}`
    }).join('\n')
  }
  if (typeof obj === 'object') {
    const entries = Object.entries(obj)
    if (entries.length === 0) return '{}'
    return entries.map(([key, val]) => {
      if (val !== null && typeof val === 'object' && (!Array.isArray(val) || val.length > 0)) {
        return `${pad}${key}:\n${toYaml(val, indent + 1)}`
      }
      return `${pad}${key}: ${toYaml(val, indent + 1)}`
    }).join('\n')
  }
  return String(obj)
}

/* ───── Shared ───── */

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