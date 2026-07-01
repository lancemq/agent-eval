import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { PromptDetail, PromptSummary } from '../api/types'
import { Modal } from '../components/Modal'

export function PromptsPage() {
  const navigate = useNavigate()
  const [prompts, setPrompts] = useState<PromptSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  async function load() {
    try {
      setPrompts(await api.prompts())
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => { load() }, [])

  if (selected) {
    return <PromptDetailPage name={selected} onBack={() => { setSelected(null); load() }} />
  }

  return (
    <section>
      <div className="page-header">
        <h2>Prompt 管理</h2>
        <button className="btn primary" onClick={() => navigate('/prompts/new')}>+ 新建 Prompt</button>
      </div>
      {message && <p className="message">{message}</p>}

      <div className="cards">
        {prompts.map((p) => (
          <div key={p.name} className="card" style={{ cursor: 'pointer' }} onClick={() => setSelected(p.name)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>{p.name}</h3>
              <span className="muted">v{p.latest_version}</span>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>{p.description || '无描述'}</p>
            <div className="actions-inline">
              <span className="muted">{p.version_count} 个版本</span>
              <span className="muted">更新于 {p.updated_at.slice(0, 10)}</span>
            </div>
          </div>
        ))}
        {prompts.length === 0 && (
          <div className="card">
            <p className="muted empty-hint">暂无 Prompt。点击 "新建 Prompt" 创建第一个。</p>
          </div>
        )}
      </div>
    </section>
  )
}

function PromptDetailPage({ name, onBack }: { name: string; onBack: () => void }) {
  const [detail, setDetail] = useState<PromptDetail | null>(null)
  const [version, setVersion] = useState<string>('')
  const [messages, setMessages] = useState<Array<Record<string, any>>>([])
  const [description, setDescription] = useState('')
  const [message, setMessage] = useState('')
  const [showDiff, setShowDiff] = useState(false)
  const [diffVersions, setDiffVersions] = useState<{ v1: string; v2: string }>({ v1: '', v2: '' })

  async function load(ver?: string) {
    try {
      const d = await api.prompt(name, ver)
      setDetail(d)
      setVersion(d.version)
      setMessages(d.messages || [])
      setDescription(d.description || '')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => { load() }, [name])

  async function save() {
    try {
      await api.updatePromptMessages(name, messages, description)
      await load()
      setMessage('已保存')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '保存失败')
    }
  }

  async function newVersion() {
    try {
      await api.addPromptVersion(name, { messages, description })
      await load()
      setMessage('新版本已创建')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '创建失败')
    }
  }

  async function remove() {
    if (!confirm(`删除 Prompt "${name}"？`)) return
    await api.deletePrompt(name)
    onBack()
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

  if (!detail) {
    return <section><div className="card"><p className="muted">加载中...</p>{message && <p className="message">{message}</p>}</div></section>
  }

  return (
    <section>
      <div className="page-header">
        <div>
          <h2>{name}</h2>
          <span className="muted">v{version}</span>
        </div>
        <div className="actions-inline">
          {detail.versions.length > 1 && (
            <select value={version} onChange={(e) => load(e.target.value)} className="search-input">
              {detail.versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
            </select>
          )}
          <button onClick={save}>保存</button>
          <button onClick={newVersion}>新版本</button>
          {detail.versions.length > 1 && <button onClick={() => { setDiffVersions({ v1: detail.versions[0].version, v2: version }); setShowDiff(true) }}>Diff</button>}
          <button className="danger" onClick={remove}>删除</button>
          <button onClick={onBack}>← 返回</button>
        </div>
      </div>
      {message && <p className="message">{message}</p>}

      <div className="card">
        <label>描述</label>
        <input className="search-input" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: '100%', marginBottom: 12 }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 className="section-title" style={{ margin: 0 }}>Messages</h3>
          <button onClick={addMessage}>+ 添加消息</button>
        </div>
        {messages.map((msg, i) => (
          <div key={i} className="card" style={{ marginBottom: 8, padding: 12 }}>
            <div className="actions-inline" style={{ marginBottom: 8 }}>
              <select value={msg.role || 'user'} onChange={(e) => updateMessage(i, 'role', e.target.value)} className="search-input" style={{ width: 120 }}>
                <option value="system">system</option>
                <option value="user">user</option>
                <option value="assistant">assistant</option>
              </select>
              <button className="danger" onClick={() => removeMessage(i)}>删除</button>
            </div>
            <textarea
              value={msg.content || ''}
              onChange={(e) => updateMessage(i, 'content', e.target.value)}
              style={{ width: '100%', minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
            />
          </div>
        ))}
        {messages.length === 0 && <p className="muted">暂无消息。点击 "+ 添加消息"。</p>}
      </div>

      {showDiff && (
        <PromptDiffModal
          name={name}
          v1={diffVersions.v1}
          v2={diffVersions.v2}
          versions={detail.versions.map((v) => v.version)}
          onClose={() => setShowDiff(false)}
          onVersionsChange={(v1, v2) => setDiffVersions({ v1, v2 })}
        />
      )}
    </section>
  )
}

function PromptDiffModal({ name, v1, v2, versions, onClose, onVersionsChange }: {
  name: string
  v1: string
  v2: string
  versions: string[]
  onClose: () => void
  onVersionsChange: (v1: string, v2: string) => void
}) {
  const [diff, setDiff] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!v1 || !v2 || v1 === v2) return
    api.diffPrompt(name, v1, v2).then(setDiff).catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
  }, [name, v1, v2])

  return (
    <Modal open={true} title={`版本对比：v${v1} vs v${v2}`} onClose={onClose} width="720px">
      <div className="actions-inline" style={{ marginBottom: 12 }}>
        <select value={v1} onChange={(e) => onVersionsChange(e.target.value, v2)} className="search-input">
          {versions.map((v) => <option key={v} value={v}>v{v}</option>)}
        </select>
        <span>→</span>
        <select value={v2} onChange={(e) => onVersionsChange(v1, e.target.value)} className="search-input">
          {versions.map((v) => <option key={v} value={v}>v{v}</option>)}
        </select>
      </div>
      {error && <p className="message">{error}</p>}
      {diff && (
        <div>
          <div className="actions-inline" style={{ marginBottom: 8 }}>
            <span className="muted">新增 {diff.summary.added}</span>
            <span className="muted">删除 {diff.summary.removed}</span>
            <span className="muted">修改 {diff.summary.modified}</span>
            <span className="muted">未变 {diff.summary.unchanged}</span>
          </div>
          {diff.modified.map((m: any, i: number) => (
            <div key={i} className="card" style={{ marginBottom: 8, padding: 8 }}>
              <p className="muted">消息 #{m.index}</p>
              {Object.entries(m.fields).map(([field, change]: [string, any]) => (
                <div key={field} style={{ marginBottom: 4 }}>
                  <strong>{field}:</strong>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <code style={{ background: 'var(--danger-bg, #fee)', padding: 4, flex: 1 }}>{JSON.stringify(change.from)}</code>
                    <code style={{ background: 'var(--success-bg, #efe)', padding: 4, flex: 1 }}>{JSON.stringify(change.to)}</code>
                  </div>
                </div>
              ))}
            </div>
          ))}
          {diff.summary.modified === 0 && diff.summary.added === 0 && diff.summary.removed === 0 && (
            <p className="muted">两个版本完全相同</p>
          )}
        </div>
      )}
    </Modal>
  )
}

export function CreatePromptPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [messages, setMessages] = useState<Array<Record<string, any>>>([{ role: 'system', content: '' }])
  const [error, setError] = useState('')

  function addMessage() {
    setMessages((prev) => [...prev, { role: 'user', content: '' }])
  }

  function updateMessage(index: number, field: string, value: string) {
    setMessages((prev) => prev.map((m, i) => i === index ? { ...m, [field]: value } : m))
  }

  function removeMessage(index: number) {
    setMessages((prev) => prev.filter((_, i) => i !== index))
  }

  async function submit() {
    try {
      await api.createPrompt({ name, messages, description })
      navigate('/prompts')
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败')
    }
  }

  return (
    <section>
      <div className="page-header">
        <h2>新建 Prompt</h2>
        <button onClick={() => navigate('/prompts')}>← 返回</button>
      </div>
      <div className="card">
        <label>名称</label>
        <input className="search-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="my_prompt" style={{ width: '100%', marginBottom: 12 }} />
        <label>描述</label>
        <input className="search-input" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: '100%', marginBottom: 12 }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h3 className="section-title" style={{ margin: 0 }}>Messages</h3>
          <button onClick={addMessage}>+ 添加消息</button>
        </div>
        {messages.map((msg, i) => (
          <div key={i} className="card" style={{ marginBottom: 8, padding: 12 }}>
            <div className="actions-inline" style={{ marginBottom: 8 }}>
              <select value={msg.role || 'user'} onChange={(e) => updateMessage(i, 'role', e.target.value)} className="search-input" style={{ width: 120 }}>
                <option value="system">system</option>
                <option value="user">user</option>
                <option value="assistant">assistant</option>
              </select>
              <button className="danger" onClick={() => removeMessage(i)}>删除</button>
            </div>
            <textarea
              value={msg.content || ''}
              onChange={(e) => updateMessage(i, 'content', e.target.value)}
              style={{ width: '100%', minHeight: 60, fontFamily: 'monospace', fontSize: 13 }}
            />
          </div>
        ))}
        {error && <p className="message">{error}</p>}
        <div className="actions-inline">
          <button className="btn primary" onClick={submit} disabled={!name}>创建</button>
          <button className="btn" onClick={() => navigate('/prompts')}>取消</button>
        </div>
      </div>
    </section>
  )
}
