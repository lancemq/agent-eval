import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { LangfuseConfig, LangfuseSession, LangfuseTrace, PluginInfo, ScorerInfo, TraceRecord, TraceSummary } from '../api/types'

type Tab = 'trace' | 'scorer' | 'plugin'

type Props = {
  selectedTraceIds: string[]
  setSelectedTraceIds: (ids: string[]) => void
  selectedScorers: string[]
  setSelectedScorers: (ids: string[]) => void
  setDraftEvalConfig: (config: any) => void
  setPage: (page: string) => void
  onEvalCreated: () => void
}

export function ResourcesPage({ selectedTraceIds, setSelectedTraceIds, selectedScorers, setSelectedScorers, setDraftEvalConfig, setPage, onEvalCreated }: Props) {
  const [tab, setTab] = useState<Tab>('trace')
  return (
    <section>
      <div className="tab-bar">
        <button className={tab === 'trace' ? 'tab active' : 'tab'} onClick={() => setTab('trace')}>Trace</button>
        <button className={tab === 'scorer' ? 'tab active' : 'tab'} onClick={() => setTab('scorer')}>Scorer</button>
        <button className={tab === 'plugin' ? 'tab active' : 'tab'} onClick={() => setTab('plugin')}>插件</button>
      </div>
      {tab === 'trace' && <TraceTab {...{ selectedTraceIds, setSelectedTraceIds, selectedScorers, setSelectedScorers, setDraftEvalConfig, setPage, onEvalCreated }} />}
      {tab === 'scorer' && <ScorerTab selectedScorers={selectedScorers} setSelectedScorers={setSelectedScorers} />}
      {tab === 'plugin' && <PluginTab />}
    </section>
  )
}

type TraceTabProps = {
  selectedTraceIds: string[]
  setSelectedTraceIds: (ids: string[]) => void
  selectedScorers: string[]
  setSelectedScorers: (ids: string[]) => void
  setDraftEvalConfig: (config: any) => void
  setPage: (page: string) => void
  onEvalCreated: () => void
}

const defaultLangfuseConfig: LangfuseConfig = { host: 'https://cloud.langfuse.com', public_key: '', project: '', enabled: false, secret_configured: false }

function TraceTab({ selectedTraceIds, setSelectedTraceIds, selectedScorers, setSelectedScorers, setDraftEvalConfig, setPage, onEvalCreated }: TraceTabProps) {
  const [subTab, setSubTab] = useState<'local' | 'langfuse'>('local')
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [activeTrace, setActiveTrace] = useState<TraceRecord | null>(null)
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  const [langfuseConfig, setLangfuseConfig] = useState<LangfuseConfig>(defaultLangfuseConfig)
  const [sessions, setSessions] = useState<LangfuseSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState('')
  const [langfuseTraces, setLangfuseTraces] = useState<LangfuseTrace[]>([])
  const [selectedLangfuseTraceIds, setSelectedLangfuseTraceIds] = useState<string[]>([])
  const [activeLangfuseTrace, setActiveLangfuseTrace] = useState<LangfuseTrace | null>(null)

  useEffect(() => {
    api.traces().then(setTraces).catch((error) => setMessage(error instanceof Error ? error.message : 'Trace 加载失败'))
    api.scorers().then((items) => { setScorers(items); if (selectedScorers.length === 0) setSelectedScorers(items.slice(0, 1).map((item) => item.type)) }).catch(console.error)
    api.langfuseConfig().then(setLangfuseConfig).catch(console.error)
  }, [])

  const filtered = useMemo(() => traces.filter((t) => `${t.trace_id} ${t.agent_name} ${t.trace_type} ${t.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [traces, query])

  function toggleTrace(traceId: string) { setSelectedTraceIds(selectedTraceIds.includes(traceId) ? selectedTraceIds.filter((id) => id !== traceId) : [...selectedTraceIds, traceId]) }
  function toggleLangfuseTrace(traceId: string) { setSelectedLangfuseTraceIds(selectedLangfuseTraceIds.includes(traceId) ? selectedLangfuseTraceIds.filter((id) => id !== traceId) : [...selectedLangfuseTraceIds, traceId]) }
  function toggleScorer(scorer: string) { setSelectedScorers(selectedScorers.includes(scorer) ? selectedScorers.filter((id) => id !== scorer) : [...selectedScorers, scorer]) }

  async function createEval() {
    if (selectedTraceIds.length === 0) return setMessage('请至少选择一个 trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    const result = await api.traceEvalConfig({ trace_ids: selectedTraceIds, scorers: selectedScorers, eval_id: `trace_eval_${Date.now()}`, name: 'Trace-based Evaluation', dimensions: ['trace_quality'], threshold: 0.7, aggregation: 'weighted' })
    setDraftEvalConfig(result.custom_eval)
    onEvalCreated()
  }

  async function testLangfuse() { const result = await api.testLangfuse(); setMessage(`Langfuse 连接成功：${result.host}，检查 sessions ${result.sessions_checked} 条`) }
  async function loadSessions() { setSessions(await api.langfuseSessions()); setMessage('Langfuse sessions 已加载') }
  async function loadSessionTraces(sessionId: string) { setActiveSessionId(sessionId); setLangfuseTraces(await api.langfuseSessionTraces(sessionId)); setSelectedLangfuseTraceIds([]) }

  async function createLangfuseEval() {
    if (selectedLangfuseTraceIds.length === 0) return setMessage('请至少选择一个 Langfuse trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    const result = await api.langfuseTraceEvalConfig({ trace_ids: selectedLangfuseTraceIds, scorers: selectedScorers, eval_id: `langfuse_eval_${Date.now()}`, name: 'Langfuse Trace Evaluation', dimensions: ['langfuse_quality'], threshold: 0.7, aggregation: 'weighted' })
    setDraftEvalConfig(result.custom_eval)
    onEvalCreated()
  }

  return (
    <>
      <div className="sub-tab-bar">
        <button className={subTab === 'local' ? 'primary' : ''} onClick={() => setSubTab('local')}>本地 Trace</button>
        <button className={subTab === 'langfuse' ? 'primary' : ''} onClick={() => setSubTab('langfuse')}>Langfuse</button>
      </div>
      {message && <p className="message">{message}</p>}
      <div className="two-column wide-left">
        {subTab === 'local' ? (
          <div className="card">
            <div className="section-title"><div><h3>选择 Trace</h3><p className="muted">从本地 trace store 选择样本，生成 custom_eval。</p></div><div className="actions-inline"><button onClick={() => setSelectedTraceIds(filtered.map((t) => t.trace_id))}>全选</button><button className="primary" onClick={createEval}>生成评测配置</button></div></div>
            <input placeholder="搜索 trace_id / agent / type / tag" value={query} onChange={(event) => setQuery(event.target.value)} />
            <table><thead><tr><th>选择</th><th>Trace ID</th><th>Agent</th><th>类型</th><th>质量</th><th>耗时</th><th>操作</th></tr></thead><tbody>{filtered.map((t) => <tr key={t.trace_id}><td><input type="checkbox" checked={selectedTraceIds.includes(t.trace_id)} onChange={() => toggleTrace(t.trace_id)} /></td><td><code>{t.trace_id}</code></td><td>{t.agent_name}</td><td><span className="status">{t.trace_type}</span></td><td>{t.quality_score.toFixed(2)}</td><td>{t.duration_ms}ms</td><td><button onClick={() => api.trace(t.trace_id).then(setActiveTrace)}>详情</button></td></tr>)}</tbody></table>
          </div>
        ) : (
          <div>
            <div className="card">
              <div className="section-title"><div><h3>Langfuse 状态</h3><p className="muted">配置请前往设置页面。</p></div><span className={`status ${langfuseConfig.enabled && langfuseConfig.secret_configured ? 'completed' : 'failed'}`}>{langfuseConfig.enabled && langfuseConfig.secret_configured ? 'configured' : 'not configured'}</span></div>
              <div className="list-row"><span>Host</span><code>{langfuseConfig.host}</code></div>
              <div className="list-row"><span>Project</span><code>{langfuseConfig.project || '-'}</code></div>
              <div className="actions-inline"><button onClick={() => setPage('settings')}>配置</button><button onClick={testLangfuse}>测试连接</button><button className="primary" onClick={loadSessions}>加载 Sessions</button></div>
            </div>
            <div className="card"><h3>Sessions</h3><table><thead><tr><th>Session</th><th>Name/User</th><th>时间</th><th>操作</th></tr></thead><tbody>{sessions.map((s) => { const id = getLangfuseId(s); return <tr key={id}><td><code>{id}</code></td><td>{s.name || s.userId || '-'}</td><td>{s.createdAt || s.updatedAt || '-'}</td><td><button className={activeSessionId === id ? 'primary' : ''} onClick={() => loadSessionTraces(id)}>加载 traces</button></td></tr> })}</tbody></table></div>
            <div className="card"><div className="section-title"><div><h3>Langfuse Traces</h3></div><button className="primary" onClick={createLangfuseEval}>生成评测配置</button></div><table><thead><tr><th>选择</th><th>Trace ID</th><th>Name</th><th>时间</th><th>操作</th></tr></thead><tbody>{langfuseTraces.map((t) => { const id = getLangfuseId(t); return <tr key={id}><td><input type="checkbox" checked={selectedLangfuseTraceIds.includes(id)} onChange={() => toggleLangfuseTrace(id)} /></td><td><code>{id}</code></td><td>{t.name || '-'}</td><td>{t.timestamp || t.createdAt || '-'}</td><td><button onClick={() => api.langfuseTrace(id).then(setActiveLangfuseTrace)}>详情</button></td></tr> })}</tbody></table></div>
          </div>
        )}
        <div>
          <ScorerPanel scorers={scorers} selectedScorers={selectedScorers} toggleScorer={toggleScorer} />
          {activeTrace && <div className="card"><h3>Trace 详情</h3><p><strong>{activeTrace.trace_id}</strong> · {activeTrace.agent_name}</p><p className="muted">输入</p><pre className="json-preview">{activeTrace.input}</pre><p className="muted">输出</p><pre className="json-preview">{activeTrace.output}</pre></div>}
          {activeLangfuseTrace && <div className="card"><h3>Langfuse Trace 详情</h3><p><strong>{getLangfuseId(activeLangfuseTrace)}</strong> · {activeLangfuseTrace.name || '-'}</p><p className="muted">输入</p><pre className="json-preview">{formatValue(activeLangfuseTrace.input)}</pre><p className="muted">输出</p><pre className="json-preview">{formatValue(activeLangfuseTrace.output)}</pre></div>}
        </div>
      </div>
    </>
  )
}

function ScorerTab({ selectedScorers, setSelectedScorers }: { selectedScorers: string[]; setSelectedScorers: (ids: string[]) => void }) {
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [query, setQuery] = useState('')
  useEffect(() => { api.scorers().then(setScorers).catch(console.error) }, [])
  const filtered = useMemo(() => scorers.filter((s) => `${s.type} ${s.description}`.toLowerCase().includes(query.toLowerCase())), [scorers, query])
  function toggle(type: string) { setSelectedScorers(selectedScorers.includes(type) ? selectedScorers.filter((item) => item !== type) : [...selectedScorers, type]) }
  return (
    <div className="card">
      <input className="search-input" placeholder="搜索 scorer 类型或描述" value={query} onChange={(event) => setQuery(event.target.value)} />
      <div className="plugin-grid list-grid">
        {filtered.map((s) => <label key={s.type} className="card plugin-card"><input type="checkbox" checked={selectedScorers.includes(s.type)} onChange={() => toggle(s.type)} /><div><strong>{s.type}</strong><p>{s.description}</p></div></label>)}
      </div>
    </div>
  )
}

function PluginTab() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [query, setQuery] = useState('')
  useEffect(() => { api.plugins().then(setPlugins).catch(console.error) }, [])
  const filtered = useMemo(() => plugins.filter((p) => `${p.name} ${p.type} ${p.description} ${p.dimensions.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [plugins, query])
  return (
    <div className="card">
      <input className="search-input" placeholder="搜索插件、类型或维度" value={query} onChange={(event) => setQuery(event.target.value)} />
      <div className="plugin-grid list-grid">
        {filtered.map((p) => <div key={p.name} className="card plugin-card standalone-card"><div><strong>{p.name}</strong><small>{p.type} · v{p.version}</small><p>{p.description || '无描述'}</p><div className="tags">{p.dimensions.map((dim) => <span key={dim}>{dim}</span>)}</div></div></div>)}
      </div>
    </div>
  )
}

function ScorerPanel({ scorers, selectedScorers, toggleScorer }: { scorers: ScorerInfo[]; selectedScorers: string[]; toggleScorer: (scorer: string) => void }) {
  return <div className="card"><h3>选择 Scorer</h3><div className="option-list">{scorers.map((s) => <label className="check-row" key={s.type}><input type="checkbox" checked={selectedScorers.includes(s.type)} onChange={() => toggleScorer(s.type)} /><span><strong>{s.type}</strong><br /><small className="muted">{s.description}</small></span></label>)}</div></div>
}

function getLangfuseId(item: LangfuseSession | LangfuseTrace): string { return String(item.id || item.sessionId || item.trace_id || '') }
function formatValue(value: any): string { if (value === undefined || value === null) return ''; return typeof value === 'string' ? value : JSON.stringify(value, null, 2) }
