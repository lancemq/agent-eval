import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
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

export function TraceListPage({ selectedTraceIds, setSelectedTraceIds, selectedScorers, setSelectedScorers, setDraftEvalConfig, setPage }: Props) {
  const [tab, setTab] = useState<Tab>('local')
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
    api.scorers().then((items) => {
      setScorers(items)
      if (selectedScorers.length === 0) setSelectedScorers(items.slice(0, 1).map((item) => item.type))
    }).catch(console.error)
    api.langfuseConfig().then(setLangfuseConfig).catch(console.error)
  }, [])

  const filtered = useMemo(() => traces.filter((trace) => `${trace.trace_id} ${trace.agent_name} ${trace.trace_type} ${trace.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [traces, query])

  function toggleTrace(traceId: string) {
    setSelectedTraceIds(selectedTraceIds.includes(traceId) ? selectedTraceIds.filter((id) => id !== traceId) : [...selectedTraceIds, traceId])
  }

  function toggleLangfuseTrace(traceId: string) {
    setSelectedLangfuseTraceIds(selectedLangfuseTraceIds.includes(traceId) ? selectedLangfuseTraceIds.filter((id) => id !== traceId) : [...selectedLangfuseTraceIds, traceId])
  }

  function toggleScorer(scorer: string) {
    setSelectedScorers(selectedScorers.includes(scorer) ? selectedScorers.filter((id) => id !== scorer) : [...selectedScorers, scorer])
  }

  async function createEval() {
    if (selectedTraceIds.length === 0) return setMessage('请至少选择一个 trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    const result = await api.traceEvalConfig({ trace_ids: selectedTraceIds, scorers: selectedScorers, eval_id: `trace_eval_${Date.now()}`, name: 'Trace-based Evaluation', dimensions: ['trace_quality'], threshold: 0.7, aggregation: 'weighted' })
    setDraftEvalConfig(result.custom_eval)
    setPage('run')
  }

  async function testLangfuse() {
    const result = await api.testLangfuse()
    setMessage(`Langfuse 连接成功：${result.host}，检查 sessions ${result.sessions_checked} 条`)
  }

  async function loadSessions() {
    setSessions(await api.langfuseSessions())
    setMessage('Langfuse sessions 已加载')
  }

  async function loadSessionTraces(sessionId: string) {
    setActiveSessionId(sessionId)
    setLangfuseTraces(await api.langfuseSessionTraces(sessionId))
    setSelectedLangfuseTraceIds([])
  }

  async function createLangfuseEval() {
    if (selectedLangfuseTraceIds.length === 0) return setMessage('请至少选择一个 Langfuse trace')
    if (selectedScorers.length === 0) return setMessage('请至少选择一个 scorer')
    const result = await api.langfuseTraceEvalConfig({ trace_ids: selectedLangfuseTraceIds, scorers: selectedScorers, eval_id: `langfuse_eval_${Date.now()}`, name: 'Langfuse Trace Evaluation', dimensions: ['langfuse_quality'], threshold: 0.7, aggregation: 'weighted' })
    setDraftEvalConfig(result.custom_eval)
    setPage('run')
  }

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
        <div className="two-column wide-left">
          <div className="card">
            <div className="section-title"><div><h3>选择 Trace</h3><p className="muted">从本地 trace store 选择样本，生成 custom_eval 任务。</p></div><div className="actions-inline"><button onClick={() => setSelectedTraceIds(filtered.map((trace) => trace.trace_id))}>选择当前结果</button><button className="primary" onClick={createEval}>生成评测配置</button></div></div>
            <input placeholder="搜索 trace_id / agent / type / tag" value={query} onChange={(event) => setQuery(event.target.value)} />
            <table><thead><tr><th>选择</th><th>Trace ID</th><th>Agent</th><th>类型</th><th>质量</th><th>耗时</th><th>操作</th></tr></thead><tbody>{filtered.map((trace) => <tr key={trace.trace_id}><td><input type="checkbox" checked={selectedTraceIds.includes(trace.trace_id)} onChange={() => toggleTrace(trace.trace_id)} /></td><td><code>{trace.trace_id}</code></td><td>{trace.agent_name}</td><td><span className="status">{trace.trace_type}</span></td><td>{trace.quality_score.toFixed(2)}</td><td>{trace.duration_ms}ms</td><td><button onClick={() => api.trace(trace.trace_id).then(setActiveTrace)}>详情</button></td></tr>)}</tbody></table>
          </div>
          <SidePanel scorers={scorers} selectedScorers={selectedScorers} toggleScorer={toggleScorer} activeTrace={activeTrace} />
        </div>
      ) : (
        <div className="two-column wide-left">
          <div>
            <div className="card">
              <div className="section-title">
                <div>
                  <h3>Langfuse 状态</h3>
                  <p className="muted">Langfuse 配置已统一迁移到配置中心。</p>
                </div>
                <span className={`status ${langfuseConfig.enabled && langfuseConfig.secret_configured ? 'completed' : 'failed'}`}>{langfuseConfig.enabled && langfuseConfig.secret_configured ? 'configured' : 'not configured'}</span>
              </div>
              <div className="list-row"><span>Host</span><code>{langfuseConfig.host}</code></div>
              <div className="list-row"><span>Project</span><code>{langfuseConfig.project || '-'}</code></div>
              <div className="actions-inline"><button onClick={() => setPage('settings')}>打开配置中心</button><button onClick={testLangfuse}>测试连接</button><button className="primary" onClick={loadSessions}>加载 Sessions</button></div>
            </div>
            <div className="card"><h3>Sessions</h3><table><thead><tr><th>Session</th><th>Name/User</th><th>时间</th><th>操作</th></tr></thead><tbody>{sessions.map((session) => { const id = getLangfuseId(session); return <tr key={id}><td><code>{id}</code></td><td>{session.name || session.userId || '-'}</td><td>{session.createdAt || session.updatedAt || '-'}</td><td><button className={activeSessionId === id ? 'primary' : ''} onClick={() => loadSessionTraces(id)}>加载 traces</button></td></tr> })}</tbody></table></div>
            <div className="card"><div className="section-title"><div><h3>Langfuse Traces</h3><p className="muted">选中 Langfuse trace 后可生成 custom_eval。</p></div><button className="primary" onClick={createLangfuseEval}>生成评测配置</button></div><table><thead><tr><th>选择</th><th>Trace ID</th><th>Name</th><th>时间</th><th>操作</th></tr></thead><tbody>{langfuseTraces.map((trace) => { const id = getLangfuseId(trace); return <tr key={id}><td><input type="checkbox" checked={selectedLangfuseTraceIds.includes(id)} onChange={() => toggleLangfuseTrace(id)} /></td><td><code>{id}</code></td><td>{trace.name || '-'}</td><td>{trace.timestamp || trace.createdAt || '-'}</td><td><button onClick={() => api.langfuseTrace(id).then(setActiveLangfuseTrace)}>详情</button></td></tr> })}</tbody></table></div>
          </div>
          <div><ScorerCard scorers={scorers} selectedScorers={selectedScorers} toggleScorer={toggleScorer} />{activeLangfuseTrace && <div className="card"><h3>Langfuse Trace 详情</h3><p><strong>{getLangfuseId(activeLangfuseTrace)}</strong> · {activeLangfuseTrace.name || '-'}</p><p className="muted">输入</p><pre className="json-preview">{formatValue(activeLangfuseTrace.input)}</pre><p className="muted">输出</p><pre className="json-preview">{formatValue(activeLangfuseTrace.output)}</pre></div>}</div>
        </div>
      )}
    </section>
  )
}

function SidePanel({ scorers, selectedScorers, toggleScorer, activeTrace }: { scorers: ScorerInfo[]; selectedScorers: string[]; toggleScorer: (scorer: string) => void; activeTrace: TraceRecord | null }) {
  return <div><ScorerCard scorers={scorers} selectedScorers={selectedScorers} toggleScorer={toggleScorer} />{activeTrace && <div className="card"><h3>Trace 详情</h3><p><strong>{activeTrace.trace_id}</strong> · {activeTrace.agent_name}</p><p className="muted">输入</p><pre className="json-preview">{activeTrace.input}</pre><p className="muted">输出</p><pre className="json-preview">{activeTrace.output}</pre></div>}</div>
}

function ScorerCard({ scorers, selectedScorers, toggleScorer }: { scorers: ScorerInfo[]; selectedScorers: string[]; toggleScorer: (scorer: string) => void }) {
  return <div className="card"><h3>选择 Scorer</h3><div className="option-list">{scorers.map((scorer) => <label className="check-row" key={scorer.type}><input type="checkbox" checked={selectedScorers.includes(scorer.type)} onChange={() => toggleScorer(scorer.type)} /><span><strong>{scorer.type}</strong><br /><small className="muted">{scorer.description}</small></span></label>)}</div></div>
}

function getLangfuseId(item: LangfuseSession | LangfuseTrace): string {
  return String(item.id || item.sessionId || item.trace_id || '')
}

function formatValue(value: any): string {
  if (value === undefined || value === null) return ''
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}
