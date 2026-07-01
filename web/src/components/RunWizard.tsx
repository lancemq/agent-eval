import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { VirtualList } from './VirtualList'
import { CustomEvalBuilder } from './CustomEvalBuilder'
import { EvaluatorSelector } from './EvaluatorSelector'
import { useAppStore } from '../stores/appStore'
import type {
  LangfuseConfig,
  LangfuseSession,
  LangfuseTrace,
  EvaluatorInfo,
  RunDefaults,
  ScorerInfo,
  TraceSummary,
} from '../api/types'

type Source = 'manual' | 'local-trace' | 'langfuse'

type Step =
  | 'source'
  | 'lf-connect'
  | 'lf-session'
  | 'lf-traces'
  | 'local-traces'
  | 'manual-config'
  | 'scorers'
  | 'preview'
  | 'run'

const STEP_LABEL: Record<Step, string> = {
  source: '选择来源',
  'lf-connect': '连接 Langfuse',
  'lf-session': '选 Session',
  'lf-traces': '选 Traces',
  'local-traces': '选本地 Trace',
  'manual-config': '编辑配置',
  scorers: '选 Scorer',
  preview: '配置预览',
  run: '启动评测',
}

function getSteps(source: Source): Step[] {
  switch (source) {
    case 'langfuse':
      return ['source', 'lf-connect', 'lf-session', 'lf-traces', 'scorers', 'preview', 'run']
    case 'local-trace':
      return ['source', 'local-traces', 'scorers', 'preview', 'run']
    case 'manual':
      return ['source', 'manual-config', 'preview', 'run']
  }
}

const fallbackRunDefaults: RunDefaults = {
  agent: 'openai:gpt-4o-mini',
  output_dir: './eval_results',
  report_formats: ['json', 'html', 'markdown'],
  orchestrator: { max_workers: 2, queue_backend: 'memory', storage: { type: 'json', output_dir: './eval_results' }, log_level: 'INFO' },
}

function buildDefaultConfig(defaults: RunDefaults) {
  return {
    orchestrator: defaults.orchestrator,
    agent: { type: 'callable', module: '', config: { model: 'gpt-4o-mini', temperature: 0 } },
    evaluators: {},
    eval_config: { priority: 'normal' },
    report: { formats: defaults.report_formats, output_dir: defaults.output_dir },
  }
}

function getLangfuseId(item: LangfuseSession | LangfuseTrace): string {
  return String((item as any).id || (item as any).sessionId || (item as any).trace_id || '')
}

export function RunWizard() {
  const navigate = useNavigate()
  const [source, setSource] = useState<Source>('langfuse')
  const [step, setStep] = useState<Step>('source')
  const [direction, setDirection] = useState<'next' | 'back'>('next')
  const [message, setMessage] = useState('')

  // Langfuse state
  const [lfConfig, setLfConfig] = useState<LangfuseConfig>({ host: '', public_key: '', project: '', enabled: false, secret_configured: false })
  const [connectStatus, setConnectStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [sessions, setSessions] = useState<LangfuseSession[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [lfTraces, setLfTraces] = useState<LangfuseTrace[]>([])
  const [loadingTraces, setLoadingTraces] = useState(false)
  const [selectedLfTraceIds, setSelectedLfTraceIds] = useState<string[]>([])
  const [lfTraceQuery, setLfTraceQuery] = useState('')

  // Local trace state
  const [localTraces, setLocalTraces] = useState<TraceSummary[]>([])
  const [localTraceQuery, setLocalTraceQuery] = useState('')
  const selectedTraceIds = useAppStore((s) => s.selectedTraceIds)
  const setSelectedTraceIds = useAppStore((s) => s.setSelectedTraceIds)

  // Scorer state
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const selectedScorers = useAppStore((s) => s.selectedScorers)
  const setSelectedScorers = useAppStore((s) => s.setSelectedScorers)
  const toggleScorer = useAppStore((s) => s.toggleScorer)

  // Manual config state
  const [evaluators, setEvaluators] = useState<EvaluatorInfo[]>([])
  const [selectedEvaluators, setSelectedEvaluators] = useState<string[]>([])
  const [runDefaults, setRunDefaults] = useState<RunDefaults>(fallbackRunDefaults)
  const [configText, setConfigText] = useState(JSON.stringify(buildDefaultConfig(fallbackRunDefaults), null, 2))

  // Preview & run
  const [previewConfig, setPreviewConfig] = useState<any>(null)
  const [agent, setAgent] = useState(fallbackRunDefaults.agent)
  const [outputDir, setOutputDir] = useState(fallbackRunDefaults.output_dir)
  const [running, setRunning] = useState(false)

  // Draft eval config from Library
  const draftEvalConfig = useAppStore((s) => s.draftEvalConfig)
  const clearDraftEvalConfig = useAppStore((s) => s.clearDraftEvalConfig)

  const steps = useMemo(() => getSteps(source), [source])
  const stepIndex = steps.indexOf(step)

  useEffect(() => {
    api.langfuseConfig().then((cfg) => {
      setLfConfig(cfg)
      if (cfg.enabled && cfg.secret_configured) setConnectStatus('ok')
    }).catch(console.error)
    api.scorers().then((items) => {
      setScorers(items)
      if (selectedScorers.length === 0) setSelectedScorers(items.slice(0, 1).map((i) => i.type))
    }).catch(console.error)
    api.evaluators().then((items) => {
      setEvaluators(items)
      setSelectedEvaluators(items.slice(0, 1).map((p) => p.name))
    }).catch(console.error)
    api.settings().then((s) => {
      setRunDefaults(s.run_defaults)
      setAgent(s.run_defaults.agent)
      setOutputDir(s.run_defaults.output_dir)
      setConfigText(JSON.stringify(buildDefaultConfig(s.run_defaults), null, 2))
    }).catch(console.error)
    api.traces().then(setLocalTraces).catch(console.error)
  }, [])

  // If a draftEvalConfig is set (from Library), prefill manual config + go to preview
  useEffect(() => {
    if (!draftEvalConfig) return
    setSource('manual')
    setConfigText(JSON.stringify({ ...buildDefaultConfig(runDefaults), evaluators: { custom_eval: draftEvalConfig } }, null, 2))
    setSelectedEvaluators((items) => items.includes('custom_eval') ? items : [...items, 'custom_eval'])
    setPreviewConfig(draftEvalConfig)
    setStep('preview')
    setMessage('已载入资源库生成的 custom_eval 配置')
    clearDraftEvalConfig()
  }, [draftEvalConfig])

  useEffect(() => { setMessage('') }, [step])

  const canGoNext = useMemo(() => {
    switch (step) {
      case 'source': return !!source
      case 'lf-connect': return connectStatus === 'ok'
      case 'lf-session': return !!selectedSessionId
      case 'lf-traces': return selectedLfTraceIds.length > 0
      case 'local-traces': return selectedTraceIds.length > 0
      case 'manual-config': {
        try { JSON.parse(configText); return true } catch { return false }
      }
      case 'scorers': return selectedScorers.length > 0
      case 'preview': return !!previewConfig
      case 'run': return !!agent
    }
  }, [step, source, connectStatus, selectedSessionId, selectedLfTraceIds, selectedTraceIds, configText, selectedScorers, previewConfig, agent])

  async function testConnect() {
    setConnectStatus('testing')
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
    try {
      setSessions(await api.langfuseSessions())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载失败')
    } finally {
      setLoadingSessions(false)
    }
  }

  async function loadLfSessionTraces(sessionId: string) {
    setLoadingTraces(true)
    try {
      const items = await api.langfuseSessionTraces(sessionId)
      setLfTraces(items)
      setSelectedLfTraceIds([])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载失败')
    } finally {
      setLoadingTraces(false)
    }
  }

  async function generateLangfusePreview() {
    try {
      const result = await api.langfuseTraceEvalConfig({
        trace_ids: selectedLfTraceIds,
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

  async function generateLocalPreview() {
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
      setPreviewConfig(result.custom_eval)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '生成配置失败')
    }
  }

  function generateManualPreview() {
    try {
      const parsed = JSON.parse(configText)
      setPreviewConfig(parsed)
    } catch (error) {
      setMessage('配置 JSON 格式错误')
    }
  }

  async function goNext() {
    if (!canGoNext) return
    const next = steps[stepIndex + 1]
    if (!next) return

    // Trigger preview generation when leaving scorers/manual-config
    if (step === 'scorers') {
      if (source === 'langfuse') await generateLangfusePreview()
      else if (source === 'local-trace') await generateLocalPreview()
    }
    if (step === 'manual-config') {
      generateManualPreview()
    }

    setDirection('next')
    setStep(next)
  }

  function goBack() {
    const prev = steps[stepIndex - 1]
    if (!prev) return
    setDirection('back')
    setStep(prev)
  }

  async function startRun() {
    setRunning(true)
    try {
      let config: any
      let evaluatorsList: string[]

      if (source === 'manual') {
        const parsed = JSON.parse(configText)
        const mergedEvaluators = { ...(parsed.evaluators || {}) }
        for (const name of selectedEvaluators) {
          mergedEvaluators[name] = { enabled: true, ...(mergedEvaluators[name] || {}) }
        }
        config = { ...parsed, evaluators: mergedEvaluators }
        evaluatorsList = selectedEvaluators
      } else {
        config = {
          orchestrator: runDefaults.orchestrator,
          agent: { type: 'callable', module: '', config: { model: agent.split(':')[1] || 'gpt-4o-mini', temperature: 0 } },
          evaluators: { custom_eval: previewConfig },
          eval_config: { priority: 'normal' },
          report: { formats: runDefaults.report_formats, output_dir: outputDir },
        }
        evaluatorsList = ['custom_eval']
      }

      const run = await api.createRun({ agent, config, evaluators: evaluatorsList, output_dir: outputDir })
      navigate(`/live/${run.run_id}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '启动失败')
      setRunning(false)
    }
  }

  const filteredLfTraces = useMemo(() => {
    if (!lfTraceQuery) return lfTraces
    const q = lfTraceQuery.toLowerCase()
    return lfTraces.filter((t) => {
      const id = getLangfuseId(t).toLowerCase()
      const name = (t.name || '').toLowerCase()
      return id.includes(q) || name.includes(q)
    })
  }, [lfTraces, lfTraceQuery])

  const filteredLocal = useMemo(
    () => localTraces.filter((t) =>
      `${t.trace_id} ${t.agent_name} ${t.trace_type} ${t.tags.join(' ')}`
        .toLowerCase()
        .includes(localTraceQuery.toLowerCase()),
    ),
    [localTraces, localTraceQuery],
  )

  return (
    <div className="wizard">
      {/* Stepper */}
      <div className="wizard-stepper">
        {steps.map((s, i) => (
          <div key={s} className={`wizard-step ${s === step ? 'active' : ''} ${i < stepIndex ? 'done' : ''}`}>
            <div className="wizard-step-num">{i < stepIndex ? '✓' : i + 1}</div>
            <div className="wizard-step-label">{STEP_LABEL[s]}</div>
          </div>
        ))}
      </div>

      {/* Content */}
      <div className={`wizard-content ${direction}`}>
        {step === 'source' && (
          <div className="wizard-pane">
            <h3>选择评测来源</h3>
            <p className="muted">不同来源对应不同的步骤流。</p>
            <div className="source-grid">
              <button className={`source-card ${source === 'langfuse' ? 'selected' : ''}`} onClick={() => setSource('langfuse')}>
                <strong>从 Langfuse Trace</strong>
                <small className="muted">连接 → 选 Session → 选 Traces → 选 Scorer</small>
              </button>
              <button className={`source-card ${source === 'local-trace' ? 'selected' : ''}`} onClick={() => setSource('local-trace')}>
                <strong>从本地 Trace</strong>
                <small className="muted">从 trace_store 选择本地样本 → 选打分器</small>
              </button>
              <button className={`source-card ${source === 'manual' ? 'selected' : ''}`} onClick={() => setSource('manual')}>
                <strong>手动配置</strong>
                <small className="muted">JSON 编辑器 + 评估器选择，适合自定义评测</small>
              </button>
            </div>
          </div>
        )}

        {step === 'lf-connect' && (
          <div className="wizard-pane">
            <h3>Langfuse 连接配置</h3>
            <p className="muted">确认 Langfuse 连接信息，测试通过后才能继续。</p>
            <div className="card form">
              <div className="list-row"><span>Host</span><code>{lfConfig.host || '-'}</code></div>
              <div className="list-row"><span>Project</span><code>{lfConfig.project || '-'}</code></div>
              <div className="list-row"><span>Public Key</span><code>{lfConfig.public_key || '-'}</code></div>
              <div className="list-row"><span>Secret Key</span><span className="muted">{lfConfig.secret_configured ? '已配置' : '未配置'}</span></div>
              <div className="list-row"><span>状态</span>
                <span className={`status ${lfConfig.enabled && lfConfig.secret_configured ? 'completed' : 'failed'}`}>
                  {lfConfig.enabled && lfConfig.secret_configured ? '已配置' : '未配置'}
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
            {(!lfConfig.enabled || !lfConfig.secret_configured) && (
              <p className="muted" style={{ marginTop: 12 }}>
                配置不完整，请先到 <button className="link-btn" onClick={() => navigate('/settings')}>设置页面</button> 完成 Langfuse 配置。
              </p>
            )}
          </div>
        )}

        {step === 'lf-session' && (
          <div className="wizard-pane">
            <h3>选择会话</h3>
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
                      <input type="radio" name="session" checked={selectedSessionId === id} onChange={() => { setSelectedSessionId(id); loadLfSessionTraces(id) }} />
                      <div className="wizard-list-meta">
                        <code>{id}</code>
                        <span className="muted">{s.name || (s as any).userId || '-'}</span>
                        <span className="muted">{s.createdAt || '-'}</span>
                      </div>
                    </label>
                  )
                })}
              </div>
            ) : (
              <div className="empty-hint">{loadingSessions ? '加载中...' : '点击刷新按钮加载会话'}</div>
            )}
          </div>
        )}

        {step === 'lf-traces' && (
          <div className="wizard-pane">
            <h3>选择 Traces</h3>
            <p className="muted">从 Session <code>{selectedSessionId}</code> 中选择要评测的 Traces。</p>
            <div className="actions-inline" style={{ marginBottom: 12 }}>
              <button onClick={() => setSelectedLfTraceIds(filteredLfTraces.map((t) => getLangfuseId(t)))}>全选</button>
              <button onClick={() => setSelectedLfTraceIds([])}>清空</button>
              <input className="search-input" placeholder="搜索 trace ID 或名称" value={lfTraceQuery} onChange={(e) => setLfTraceQuery(e.target.value)} />
              <span className="muted">已选 {selectedLfTraceIds.length} / {lfTraces.length}</span>
            </div>
            {loadingTraces ? (
              <div className="empty-hint">加载中...</div>
            ) : filteredLfTraces.length === 0 ? (
              <div className="empty-hint">暂无 Traces</div>
            ) : (
              <div className="wizard-virtual-list">
                <VirtualList
                  className="row-list row-list-virtual"
                  items={filteredLfTraces}
                  itemHeight={56}
                  getKey={(t, i) => getLangfuseId(t) || `t-${i}`}
                  renderItem={(t) => {
                    const id = getLangfuseId(t)
                    const checked = selectedLfTraceIds.includes(id)
                    return (
                      <div className="compact-row">
                        <input type="checkbox" checked={checked} onChange={() => {
                          setSelectedLfTraceIds(checked ? selectedLfTraceIds.filter((x) => x !== id) : [...selectedLfTraceIds, id])
                        }} />
                        <div className="compact-row-main">
                          <div className="compact-row-title"><code>{id}</code></div>
                          <div className="compact-row-meta">
                            <span>{t.name || '-'}</span>
                            <span>·</span>
                            <span>{t.timestamp || t.createdAt || '-'}</span>
                          </div>
                        </div>
                      </div>
                    )
                  }}
                />
              </div>
            )}
          </div>
        )}

        {step === 'local-traces' && (
          <div className="wizard-pane">
            <h3>选择本地 Trace</h3>
            <p className="muted">从本地 trace store选择评测样本。</p>
            <div className="actions-inline" style={{ marginBottom: 12 }}>
              <button onClick={() => setSelectedTraceIds(filteredLocal.map((t) => t.trace_id))}>全选</button>
              <button onClick={() => setSelectedTraceIds([])}>清空</button>
              <input className="search-input" placeholder="搜索 trace_id / agent / type / tag" value={localTraceQuery} onChange={(e) => setLocalTraceQuery(e.target.value)} />
              <span className="muted">已选 {selectedTraceIds.length} / {localTraces.length}</span>
            </div>
            {filteredLocal.length === 0 ? (
              <div className="empty-hint">{localTraceQuery ? '没有匹配的结果' : '本地 trace store为空'}</div>
            ) : (
              <div className="wizard-virtual-list">
                <VirtualList
                  className="row-list row-list-virtual"
                  items={filteredLocal}
                  itemHeight={56}
                  getKey={(t) => t.trace_id}
                  renderItem={(trace) => {
                    const checked = selectedTraceIds.includes(trace.trace_id)
                    return (
                      <div className="compact-row">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            setSelectedTraceIds(checked ? selectedTraceIds.filter((id) => id !== trace.trace_id) : [...selectedTraceIds, trace.trace_id])
                          }}
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
              </div>
            )}
          </div>
        )}

        {step === 'manual-config' && (
          <div className="wizard-pane">
            <h3>编辑评测配置</h3>
            <p className="muted">在 JSON 中调整评估器配置，或用右侧 Custom Eval Builder 辅助。</p>
            <div className="two-column modal-form">
              <div className="form">
                <label>配置 JSON</label>
                <textarea
                  value={configText}
                  onChange={(e) => setConfigText(e.target.value)}
                  style={{ minHeight: 360, fontFamily: 'var(--mono, monospace)' }}
                />
              </div>
              <div>
                <CustomEvalBuilder
                  config={(() => { try { return JSON.parse(configText) } catch { return buildDefaultConfig(runDefaults) } })()}
                  onApply={(c) => setConfigText(JSON.stringify(c, null, 2))}
                />
                <div className="card">
                  <h3>选择评估器</h3>
                  <EvaluatorSelector evaluators={evaluators} selected={selectedEvaluators} onChange={setSelectedEvaluators} />
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 'scorers' && (
          <div className="wizard-pane">
            <h3>选择打分器</h3>
            <p className="muted">选择用于评测的 Scorer，可多选。</p>
            <div className="wizard-list compact">
              {scorers.map((s) => (
                <label key={s.type} className={`wizard-list-item ${selectedScorers.includes(s.type) ? 'selected' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedScorers.includes(s.type)}
                    onChange={() => toggleScorer(s.type)}
                  />
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
            <p className="muted">确认将要使用的评测配置。</p>
            {previewConfig ? (
              <div className="card" style={{ maxHeight: 420, overflow: 'auto' }}>
                <pre className="json-preview">{JSON.stringify(previewConfig, null, 2)}</pre>
              </div>
            ) : (
              <div className="empty-hint">正在生成...</div>
            )}
            <div className="card" style={{ marginTop: 12 }}>
              {source === 'langfuse' && <div className="stat-row"><span>Langfuse Trace</span><strong>{selectedLfTraceIds.length}</strong></div>}
              {source === 'local-trace' && <div className="stat-row"><span>本地 Trace</span><strong>{selectedTraceIds.length}</strong></div>}
              {source !== 'manual' && <div className="stat-row"><span>打分器</span><strong>{selectedScorers.length}</strong></div>}
              {source === 'manual' && <div className="stat-row"><span>评估器</span><strong>{selectedEvaluators.length}</strong></div>}
            </div>
          </div>
        )}

        {step === 'run' && (
          <div className="wizard-pane">
            <h3>启动实验</h3>
            <p className="muted">设置 Agent 和输出目录后启动实验，可在「实验监测」查看进度。</p>
            <div className="card form">
              <label>Agent Spec</label>
              <input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="openai:gpt-4o-mini" />
              <label>输出目录</label>
              <input value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
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
