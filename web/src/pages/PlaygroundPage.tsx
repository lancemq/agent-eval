import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PlaygroundResult, PromptSummary, ScorerInfo } from '../api/types'

export function PlaygroundPage() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([])
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [selectedPrompt, setSelectedPrompt] = useState('')
  const [messages, setMessages] = useState<Array<Record<string, any>>>([
    { role: 'system', content: 'You are a helpful AI assistant.' },
  ])
  const [model, setModel] = useState('gpt-4o-mini')
  const [input, setInput] = useState('')
  const [expected, setExpected] = useState('')
  const [selectedScorers, setSelectedScorers] = useState<string[]>([])
  const [result, setResult] = useState<PlaygroundResult | null>(null)
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.prompts().then(setPrompts).catch(console.error)
    api.scorers().then((items) => {
      setScorers(items)
      if (items.length > 0) setSelectedScorers([items[0].type])
    }).catch(console.error)
  }, [])

  async function loadPrompt(name: string) {
    if (!name) return
    try {
      const d = await api.prompt(name)
      if (d.messages && d.messages.length > 0) {
        setMessages(d.messages)
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载 Prompt 失败')
    }
  }

  function toggleScorer(type: string) {
    setSelectedScorers((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    )
  }

  function updateMessage(index: number, field: string, value: string) {
    setMessages((prev) => prev.map((m, i) => i === index ? { ...m, [field]: value } : m))
  }

  function addMessage() {
    setMessages((prev) => [...prev, { role: 'user', content: '' }])
  }

  function removeMessage(index: number) {
    setMessages((prev) => prev.filter((_, i) => i !== index))
  }

  async function run() {
    if (!input.trim()) {
      setMessage('请输入测试输入')
      return
    }
    setRunning(true)
    setMessage('')
    setResult(null)
    try {
      const res = await api.playgroundRun({
        messages,
        model,
        input,
        scorers: selectedScorers,
        expected: expected || undefined,
      })
      setResult(res)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '运行失败')
    } finally {
      setRunning(false)
    }
  }

  return (
    <section>
      <div className="page-header">
        <h2>Playground</h2>
        <span className="muted">单次调试：Prompt + Model + Scorer</span>
      </div>
      {message && <p className="message">{message}</p>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* 左栏：配置 */}
        <div>
          <div className="card" style={{ marginBottom: 12 }}>
            <h3 className="section-title">Prompt</h3>
            <div className="actions-inline" style={{ marginBottom: 8 }}>
              <select
                value={selectedPrompt}
                onChange={(e) => { setSelectedPrompt(e.target.value); loadPrompt(e.target.value) }}
                className="search-input"
                style={{ flex: 1 }}
              >
                <option value="">直接编辑（不加载）</option>
                {prompts.map((p) => <option key={p.name} value={p.name}>{p.name} (v{p.latest_version})</option>)}
              </select>
            </div>
            {messages.map((msg, i) => (
              <div key={i} className="card" style={{ marginBottom: 8, padding: 8 }}>
                <div className="actions-inline" style={{ marginBottom: 4 }}>
                  <select value={msg.role || 'user'} onChange={(e) => updateMessage(i, 'role', e.target.value)} className="search-input" style={{ width: 100 }}>
                    <option value="system">system</option>
                    <option value="user">user</option>
                    <option value="assistant">assistant</option>
                  </select>
                  {messages.length > 1 && <button className="danger" onClick={() => removeMessage(i)}>删除</button>}
                </div>
                <textarea
                  value={msg.content || ''}
                  onChange={(e) => updateMessage(i, 'content', e.target.value)}
                  style={{ width: '100%', minHeight: 40, fontSize: 12, fontFamily: 'monospace' }}
                />
              </div>
            ))}
            <button onClick={addMessage}>+ 添加消息</button>
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            <h3 className="section-title">模型与输入</h3>
            <label>Model</label>
            <input className="search-input" value={model} onChange={(e) => setModel(e.target.value)} style={{ width: '100%', marginBottom: 8 }} />
            <label>测试输入</label>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              style={{ width: '100%', minHeight: 80, fontSize: 12, fontFamily: 'monospace', marginBottom: 8 }}
              placeholder="输入测试文本..."
            />
            <label>期望输出（可选，用于打分器参考）</label>
            <textarea
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
              style={{ width: '100%', minHeight: 40, fontSize: 12, fontFamily: 'monospace' }}
              placeholder="期望输出..."
            />
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            <h3 className="section-title">打分器（{selectedScorers.length} 已选）</h3>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {scorers.map((s) => (
                <label key={s.type} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0', cursor: 'pointer' }}>
                  <input type="checkbox" checked={selectedScorers.includes(s.type)} onChange={() => toggleScorer(s.type)} />
                  <span style={{ fontWeight: 500 }}>{s.type}</span>
                  <span className="muted" style={{ fontSize: 11 }}>{s.description}</span>
                </label>
              ))}
            </div>
          </div>

          <button className="btn primary" onClick={run} disabled={running} style={{ width: '100%' }}>
            {running ? '运行中...' : '运行'}
          </button>
        </div>

        {/* 右栏：结果 */}
        <div>
          {result ? (
            <>
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <h3 className="section-title" style={{ margin: 0 }}>输出</h3>
                  <span className="muted">{result.latency_ms}ms</span>
                </div>
                {result.error ? (
                  <p className="message" style={{ color: 'var(--danger, #c0392b)' }}>{result.error}</p>
                ) : (
                  <pre style={{ background: 'var(--bg-secondary, #f5f5f5)', padding: 12, borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {result.output}
                  </pre>
                )}
              </div>

              {!result.error && result.scores.length > 0 && (
                <div className="card">
                  <h3 className="section-title">评分结果</h3>
                  {result.scores.map((s) => (
                    <div key={s.name} className="card" style={{ marginBottom: 8, padding: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <strong>{s.name}</strong>
                        <span style={{ fontWeight: 700, color: s.passed ? 'var(--success, #27ae60)' : 'var(--danger, #c0392b)' }}>
                          {s.score.toFixed(3)}
                        </span>
                      </div>
                      {s.reason && <p className="muted" style={{ margin: 0, fontSize: 12 }}>{s.reason}</p>}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="card">
              <p className="muted empty-hint">配置左侧参数后点击「运行」查看结果</p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
