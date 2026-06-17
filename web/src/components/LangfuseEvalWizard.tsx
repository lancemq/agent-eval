import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { LangfuseConfig, LangfuseSession, LangfuseTrace, ScorerInfo } from '../api/types'

type Step = 'connect' | 'session' | 'traces' | 'scorers' | 'preview' | 'run'

const STEP_LABELS: Record<Step, string> = {
  connect: '连接配置',
  session: '选择 Session',
  traces: '选择 Traces',
  scorers: '选择 Scorer',
  preview: '配置预览',
  run: '启动评测',
}

const STEP_ORDER: Step[] = ['connect', 'session', 'traces', 'scorers', 'preview', 'run']

function getLangfuseId(item: LangfuseSession | LangfuseTrace): string {
  return String(item.id || item.sessionId || item.trace_id || '')
}

function formatPreview(value: any): string {
  if (value === undefined || value === null) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 200 ? text.slice(0, 200) + '...' : text
}

type Props = {
  onClose: () => void
  onCreated: (runId: string) => void
}

export function LangfuseEvalWizard({ onClose, onCreated }: Props) {
  const [step, setStep] = useState<Step>('connect')
  const [direction, setDirection] = useState<'next' | 'back'>('next')
  const [message, setMessage] = useState('')

  // Step: connect
  const [config, setConfig] = useState<LangfuseConfig>({ host: '', public_key: '', project: '', enabled: false, secret_configured: false })
  const [connectStatus, setConnectStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')

  // Step: session
  const [sessions, setSessions] = useState<LangfuseSession[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [loadingSessions, setLoadingSessions] = useState(false)

  // Step: traces
  const [traces, setTraces] = useState<LangfuseTrace[]>([])
  const [selectedTraceIds, setSelectedTraceIds] = useState<string[]>([])
  const [loadingTraces, setLoadingTraces] = useState(false)
  const [traceQuery, setTraceQuery] = useState('')

  // Step: scorers
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [selectedScorers, setSelectedScorers] = useState<string[]>([])

  // Step: preview & run
  const [previewConfig, setPreviewConfig] = useState<any>(null)
  const [agent, setAgent] = useState('openai:gpt-4o-mini')
  const [outputDir, setOutputDir] = useState('./eval_results')
  const [running, setRunning] = useState(false)

  const stepIndex = STEP_ORDER.indexOf(step)
  const canGoNext = useMemo(() => {
    switch (step) {
      case 'connect': return connectStatus === 'ok'
      case 'session': return !!selectedSessionId
      case 'traces': return selectedTraceIds.length > 0
      case 'scorers': return selectedScorers.length > 0
      case 'preview': return !!previewConfig
      case 'run': return !!agent
    }
  }, [step, connectStatus, selectedSessionId, selectedTraceIds, selectedScorers, previewConfig, agent])

  useEffect(() => {
    api.langfuseConfig().then((cfg) => {
      setConfig(cfg)
      if (cfg.enabled && cfg.secret_configured) {
        setConnectStatus('ok')
      }
    }).catch(console.error)
    api.scorers().then(setScorers).catch(console.error)
  }, [])

  useEffect(() => {
    setMessage('')
  }, [step])

  async function testConnect() {
    setConnectStatus('testing')
    setMessage('')
    try {
      await api.testLangfuse()
      setConnectStatus('ok')
      setMessage('连接成功')
    } catch (error) {
      setConnectStatus('error')
      setMessage(error instanceof Error ? error.message : '连接失败')
    }
  }

  async function loadSessions() {
    setLoadingSessions(true)
    setMessage('')
    try {
      const items = await api.langfuseSessions()
      setSessions(items)
      if (items.length === 0) setMessage('暂无 Sessions')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载失败')
    } finally {
      setLoadingSessions(false)
    }
  }

  async function loadTraces(sessionId: string) {
    setLoadingTraces(true)
    setMessage('')
    try {
      const items = await api.langfuseSessionTraces(sessionId)
      setTraces(items)
      setSelectedTraceIds([])
      if (items.length === 0) setMessage('该 Session 暂无 Traces')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载失败')
    } finally {
      setLoadingTraces(false)
    }
  }

  async function generatePreview() {
    setMessage('')
    try {
      const result = await api.langfuseTraceEvalConfig({
        trace_ids: selectedTraceIds,
        scorers: selectedScorers,
        eval_id: `langfuse_eval_${Date.now()}`,
        name: 'Langfuse Trace Evaluation',
        dimensions: ['langfuse_quality'],
        threshold: 0.7,
        aggregation: 'weighted',
      })
      setPreviewConfig(result.custom_eval)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '生成配置失败')
    }
  }

  async function startRun() {
    if (!previewConfig || !agent) return
    setRunning(true)
    setMessage('')
    try {
      const config = {
        orchestrator: { max_workers: 2, queue_backend: 'memory', storage: { type: 'json', output_dir: outputDir }, log_level: 'INFO' },
        agent: { type: 'callable', module: '', config: { model: agent.split(':')[1] || 'gpt-4o-mini', temperature: 0 } },
        plugins: { custom_eval: previewConfig },
        eval_config: { priority: 'normal' },
        report: { formats: ['json', 'html', 'markdown'], output_dir: outputDir },
      }
      const run = await api.createRun({ agent, config, plugins: ['custom_eval'], output_dir: outputDir })
      onCreated(run.run_id)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '启动失败')
      setRunning(false)
    }
  }

  function goNext() {
    if (!canGoNext) return
    const next = STEP_ORDER[stepIndex + 1]
    if (!next) return
    setDirection('next')
    if (step === 'scorers') generatePreview()
    setStep(next)
  }

  function goBack() {
    const prev = STEP_ORDER[stepIndex - 1]
    if (!prev) return
    setDirection('back')
    setStep(prev)
  }

  const filteredTraces = useMemo(() => {
    if (!traceQuery) return traces
    const q = traceQuery.toLowerCase()
    return traces.filter((t) => {
      const id = getLangfuseId(t).toLowerCase()
      const name = (t.name || '').toLowerCase()
      return id.includes(q) || name.includes(q)
    })
  }, [traces, traceQuery])

  return (
    <div className="wizard">
      {/* Stepper */}
      <div className="wizard-stepper">
        {STEP_ORDER.map((s, i) => (
          <div key={s} className={`wizard-step ${s === step ? 'active' : ''} ${i < stepIndex ? 'done' : ''}`}>
            <div className="wizard-step-num">{i < stepIndex ? '✓' : i + 1}</div>
            <div className="wizard-step-label">{STEP_LABELS[s]}</div>
          </div>
        ))}
      </div>

      {/* Content */}
      <div className={`wizard-content ${direction}`}>
        {step === 'connect' && (
          <div className="wizard-pane">
            <h3>Langfuse 连接配置</h3>
            <p className="muted">确认 Langfuse 连接信息，测试通过后才能继续。</p>
            <div className="card form">
              <div className="list-row"><span>Host</span><code>{config.host || '-'}</code></div>
              <div className="list-row"><span>Project</span><code>{config.project || '-'}</code></div>
              <div className="list-row"><span>Public Key</span><code>{config.public_key || '-'}</code></div>
              <div className="list-row"><span>Secret Key</span><span className="muted">{config.secret_configured ? '已配置' : '未配置'}</span></div>
              <div className="list-row"><span>状态</span>
                <span className={`status ${config.enabled && config.secret_configured ? 'completed' : 'failed'}`}>
                  {config.enabled && config.secret_configured ? '已配置' : '未配置'}
                </span>
              </div>
              <div className="actions-inline" style={{ marginTop: 8 }}>
                <button onClick={testConnect} disabled={connectStatus === 'testing'}>
                  {connectStatus === 'testing' ? '测试中...' : '测试连接'}
                </button>
                {connectStatus === 'ok' && <span className="status completed">连接正常</span>}
                {connectStatus === 'error' && <span className="status failed">连接失败</span>}
              </div>
            </div>
            {(!config.enabled || !config.secret_configured) && (
              <p className="muted" style={{ marginTop: 12 }}>
                配置不完整，请先到 <button className="link-btn" onClick={() => { onClose(); /* navigate to settings handled by caller if needed */ }}>设置页面</button> 完成 Langfuse 配置。
              </p>
            )}
          </div>
        )}

        {step === 'session' && (
          <div className="wizard-pane">
            <h3>选择 Session</h3>
            <p className="muted">从 Langfuse 中选择一个 Session，加载其中的 Traces。</p>
            <div className="actions-inline" style={{ marginBottom: 12 }}>
              <button onClick={loadSessions} disabled={loadingSessions}>
                {loadingSessions ? '加载中...' : '刷新 Sessions'}
              </button>
              <span className="muted">共 {sessions.length} 个 Session</span>
            </div>
            {sessions.length > 0 ? (
              <div className="wizard-list">
                {sessions.map((s) => {
                  const id = getLangfuseId(s)
                  return (
                    <label key={id} className={`wizard-list-item ${selectedSessionId === id ? 'selected' : ''}`}>
                      <input type="radio" name="session" checked={selectedSessionId === id} onChange={() => { setSelectedSessionId(id); loadTraces(id) }} />
                      <div className="wizard-list-meta">
                        <code>{id}</code>
                        <span className="muted">{s.name || s.userId || '-'}</span>
                        <span className="muted">{s.createdAt || '-'}</span>
                      </div>
                    </label>
                  )
                })}
              </div>
            ) : (
              <div className="empty-hint">{loadingSessions ? '加载中...' : '点击刷新按钮加载 Sessions'}</div>
            )}
          </div>
        )}

        {step === 'traces' && (
          <div className="wizard-pane">
            <h3>选择 Traces</h3>
            <p className="muted">从 Session <code>{selectedSessionId}</code> 中选择要评测的 Traces。</p>
            <div className="actions-inline" style={{ marginBottom: 12 }}>
              <button onClick={() => setSelectedTraceIds(filteredTraces.map((t) => getLangfuseId(t)))}>全选</button>
              <button onClick={() => setSelectedTraceIds([])}>清空</button>
              <input className="search-input" placeholder="搜索 trace ID 或名称" value={traceQuery} onChange={(e) => setTraceQuery(e.target.value)} />
              <span className="muted">已选 {selectedTraceIds.length} / {traces.length}</span>
            </div>
            {loadingTraces ? (
              <div className="empty-hint">加载中...</div>
            ) : filteredTraces.length > 0 ? (
              <div className="wizard-list compact">
                {filteredTraces.map((t) => {
                  const id = getLangfuseId(t)
                  return (
                    <label key={id} className={`wizard-list-item ${selectedTraceIds.includes(id) ? 'selected' : ''}`}>
                      <input type="checkbox" checked={selectedTraceIds.includes(id)} onChange={() => {
                        setSelectedTraceIds(selectedTraceIds.includes(id) ? selectedTraceIds.filter((x) => x !== id) : [...selectedTraceIds, id])
                      }} />
                      <div className="wizard-list-meta">
                        <code>{id}</code>
                        <span className="muted">{t.name || '-'}</span>
                        <span className="muted">{t.timestamp || t.createdAt || '-'}</span>
                      </div>
                      <div className="wizard-list-preview muted">{formatPreview(t.input)}</div>
                    </label>
                  )
                })}
              </div>
            ) : (
              <div className="empty-hint">暂无 Traces</div>
            )}
          </div>
        )}

        {step === 'scorers' && (
          <div className="wizard-pane">
            <h3>选择 Scorer</h3>
            <p className="muted">选择用于评测的 Scorer，可多选。</p>
            <div className="wizard-list compact">
              {scorers.map((s) => (
                <label key={s.type} className={`wizard-list-item ${selectedScorers.includes(s.type) ? 'selected' : ''}`}>
                  <input type="checkbox" checked={selectedScorers.includes(s.type)} onChange={() => {
                    setSelectedScorers(selectedScorers.includes(s.type) ? selectedScorers.filter((x) => x !== s.type) : [...selectedScorers, s.type])
                  }} />
                  <div className="wizard-list-meta">
                    <strong>{s.type}</strong>
                    <span className="muted">{s.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}

        {step === 'preview' && (
          <div className="wizard-pane">
            <h3>配置预览</h3>
            <p className="muted">确认将要生成的评测配置。</p>
            {previewConfig ? (
              <div className="card" style={{ maxHeight: 420, overflow: 'auto' }}>
                <pre className="json-preview">{JSON.stringify(previewConfig, null, 2)}</pre>
              </div>
            ) : (
              <div className="empty-hint">正在生成...</div>
            )}
            <div className="card" style={{ marginTop: 12 }}>
              <div className="stat-row"><span>评测 Trace 数</span><strong>{selectedTraceIds.length}</strong></div>
              <div className="stat-row"><span>Scorer 数</span><strong>{selectedScorers.length}</strong></div>
              <div className="stat-row"><span>Session</span><strong><code>{selectedSessionId}</code></strong></div>
            </div>
          </div>
        )}

        {step === 'run' && (
          <div className="wizard-pane">
            <h3>启动评测</h3>
            <p className="muted">设置 Agent 和输出目录，然后启动评测。</p>
            <div className="card form">
              <label>Agent Spec</label>
              <input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="openai:gpt-4o-mini" />
              <label>输出目录</label>
              <input value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
            </div>
            <div className="card" style={{ marginTop: 12 }}>
              <div className="stat-row"><span>评测 Trace 数</span><strong>{selectedTraceIds.length}</strong></div>
              <div className="stat-row"><span>Scorer</span><strong>{selectedScorers.join(', ')}</strong></div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="wizard-footer">
        {message && <p className="message">{message}</p>}
        <div className="wizard-actions">
          {stepIndex > 0 && <button onClick={goBack}>上一步</button>}
          {step !== 'run' ? (
            <button className="primary" onClick={goNext} disabled={!canGoNext}>下一步</button>
          ) : (
            <button className="primary" onClick={startRun} disabled={running || !canGoNext}>
              {running ? '启动中...' : '启动评测'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
