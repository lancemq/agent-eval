import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ReviewDetail, ReviewItem, ReviewSummary } from '../api/types'
import { Modal } from '../components/Modal'

export function ReviewsPage() {
  const { name: selectedName } = useParams()
  const navigate = useNavigate()
  const [reviews, setReviews] = useState<ReviewSummary[]>([])
  const [message, setMessage] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  async function load() {
    try {
      setReviews(await api.reviews())
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => { load() }, [])

  if (selectedName) {
    return <ReviewDetailPage name={selectedName} onBack={() => navigate('/reviews')} />
  }

  return (
    <section>
      <div className="page-header">
        <h2>人工评审</h2>
        <button className="btn primary" onClick={() => setShowCreate(true)}>+ 新建评审</button>
      </div>
      {message && <p className="message">{message}</p>}

      <div className="cards">
        {reviews.map((r) => (
          <div key={r.name} className="card" style={{ cursor: 'pointer' }} onClick={() => navigate(`/reviews/${r.name}`)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>{r.name}</h3>
              <span className="muted">v{r.latest_version}</span>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>{r.description || '无描述'}</p>
            <div className="actions-inline">
              <span className="muted">{r.item_count} 条</span>
              {r.pending_count > 0 && <span style={{ color: 'var(--warning, #e67e22)' }}>{r.pending_count} 待评审</span>}
              <span className="muted">{r.version_count} 个版本</span>
            </div>
          </div>
        ))}
        {reviews.length === 0 && (
          <div className="card">
            <p className="muted empty-hint">暂无评审会话。点击 "+ 新建评审" 创建。</p>
          </div>
        )}
      </div>

      {showCreate && <CreateReviewModal onClose={() => setShowCreate(false)} onCreated={(name) => { setShowCreate(false); navigate(`/reviews/${name}`) }} />}
    </section>
  )
}

function CreateReviewModal({ onClose, onCreated }: { onClose: () => void; onCreated: (name: string) => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [output, setOutput] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      const items = output.trim() ? output.split('\n---\n').map((text) => ({ output: text.trim(), status: 'pending' })) : []
      const result = await api.createReview({ name, items, description })
      onCreated(result.name)
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败')
    }
  }

  return (
    <Modal open={true} title="新建评审会话" onClose={onClose}>
      <div className="card form">
        <label>名称</label>
        <input className="search-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="review_batch_1" />
        <label>描述</label>
        <input className="search-input" value={description} onChange={(e) => setDescription(e.target.value)} />
        <label>评审内容（每条用 --- 分隔）</label>
        <textarea
          value={output}
          onChange={(e) => setOutput(e.target.value)}
          style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 13 }}
          placeholder="第一条输出&#10;---&#10;第二条输出"
        />
        {error && <p className="message">{error}</p>}
        <div className="actions-inline">
          <button className="btn primary" onClick={submit} disabled={!name}>创建</button>
          <button className="btn" onClick={onClose}>取消</button>
        </div>
      </div>
    </Modal>
  )
}

function ReviewDetailPage({ name, onBack }: { name: string; onBack: () => void }) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [version, setVersion] = useState('')
  const [message, setMessage] = useState('')
  const [adding, setAdding] = useState(false)

  async function load(ver?: string) {
    try {
      const d = await api.review(name, ver)
      setDetail(d)
      setVersion(d.version)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => { load() }, [name])

  async function updateItem(itemId: string, status: string) {
    try {
      const d = await api.updateReviewItem(name, itemId, { status })
      setDetail(d)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '更新失败')
    }
  }

  async function updateNotes(itemId: string, notes: string) {
    try {
      const d = await api.updateReviewItem(name, itemId, { notes })
      setDetail(d)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '更新失败')
    }
  }

  async function remove() {
    if (!confirm(`删除评审 "${name}"？`)) return
    await api.deleteReview(name)
    onBack()
  }

  if (!detail) {
    return <section><div className="card"><p className="muted">加载中...</p>{message && <p className="message">{message}</p>}</div></section>
  }

  const pending = detail.items.filter((i) => i.status === 'pending').length
  const approved = detail.items.filter((i) => i.status === 'approved').length
  const rejected = detail.items.filter((i) => i.status === 'rejected').length

  return (
    <section>
      <div className="page-header">
        <div>
          <h2>{name}</h2>
          <span className="muted">v{version} · {detail.items.length} 条 · {pending} 待审 · {approved} 通过 · {rejected} 驳回</span>
        </div>
        <div className="actions-inline">
          {detail.versions.length > 1 && (
            <select value={version} onChange={(e) => load(e.target.value)} className="search-input">
              {detail.versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
            </select>
          )}
          <button onClick={() => setAdding(true)}>+ 添加条目</button>
          <button className="danger" onClick={remove}>删除</button>
          <button onClick={onBack}>← 返回</button>
        </div>
      </div>
      {message && <p className="message">{message}</p>}

      {detail.items.map((item) => (
        <ReviewItemCard key={item.item_id} item={item} onStatusChange={(s) => updateItem(item.item_id, s)} onNotesChange={(n) => updateNotes(item.item_id, n)} />
      ))}
      {detail.items.length === 0 && <div className="card"><p className="muted empty-hint">暂无评审条目</p></div>}

      {adding && <AddItemsModal name={name} onClose={() => setAdding(false)} onAdded={() => { setAdding(false); load() }} />}
    </section>
  )
}

function ReviewItemCard({ item, onStatusChange, onNotesChange }: {
  item: ReviewItem
  onStatusChange: (status: string) => void
  onNotesChange: (notes: string) => void
}) {
  const [notes, setNotes] = useState(item.notes)
  const statusColor = item.status === 'approved' ? 'var(--success, #27ae60)' : item.status === 'rejected' ? 'var(--danger, #c0392b)' : item.status === 'changes_requested' ? 'var(--warning, #e67e22)' : 'var(--muted, #888)'

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div>
          {item.trace_id && <span className="muted">trace: <code>{item.trace_id.slice(0, 12)}</code></span>}
          {item.task_id && <span className="muted" style={{ marginLeft: 8 }}>task: <code>{item.task_id}</code></span>}
        </div>
        <span style={{ color: statusColor, fontWeight: 600 }}>{item.status}</span>
      </div>
      <pre style={{ background: 'var(--bg-secondary, #f5f5f5)', padding: 8, borderRadius: 4, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '4px 0' }}>{item.output}</pre>
      {item.expected && (
        <div style={{ marginTop: 4 }}>
          <span className="muted">期望输出：</span>
          <pre style={{ background: 'var(--bg-tertiary, #fafafa)', padding: 8, borderRadius: 4, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '4px 0' }}>{item.expected}</pre>
        </div>
      )}
      {item.labels.length > 0 && (
        <div className="actions-inline" style={{ marginTop: 4 }}>
          {item.labels.map((l) => <span key={l} className="tag" style={{ background: 'var(--bg-secondary, #eee)', padding: '2px 8px', borderRadius: 12, fontSize: 11 }}>{l}</span>)}
        </div>
      )}
      <div style={{ marginTop: 8 }}>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== item.notes && onNotesChange(notes)}
          placeholder="评审备注..."
          style={{ width: '100%', minHeight: 40, fontSize: 13 }}
        />
      </div>
      <div className="actions-inline" style={{ marginTop: 8 }}>
        <button onClick={() => onStatusChange('approved')} style={item.status === 'approved' ? { fontWeight: 700, color: 'var(--success, #27ae60)' } : {}}>通过</button>
        <button onClick={() => onStatusChange('rejected')} style={item.status === 'rejected' ? { fontWeight: 700, color: 'var(--danger, #c0392b)' } : {}}>驳回</button>
        <button onClick={() => onStatusChange('changes_requested')} style={item.status === 'changes_requested' ? { fontWeight: 700, color: 'var(--warning, #e67e22)' } : {}}>需修改</button>
        <button onClick={() => onStatusChange('pending')}>重置</button>
      </div>
    </div>
  )
}

function AddItemsModal({ name, onClose, onAdded }: { name: string; onClose: () => void; onAdded: () => void }) {
  const [output, setOutput] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      const items = output.trim() ? output.split('\n---\n').map((text) => ({ output: text.trim(), status: 'pending' })) : []
      if (items.length === 0) return
      await api.addReviewItems(name, items)
      onAdded()
    } catch (e) {
      setError(e instanceof Error ? e.message : '添加失败')
    }
  }

  return (
    <Modal open={true} title="添加评审条目" onClose={onClose}>
      <div className="card form">
        <label>评审内容（每条用 --- 分隔）</label>
        <textarea
          value={output}
          onChange={(e) => setOutput(e.target.value)}
          style={{ width: '100%', minHeight: 120, fontFamily: 'monospace', fontSize: 13 }}
          placeholder="第一条输出&#10;---&#10;第二条输出"
        />
        {error && <p className="message">{error}</p>}
        <div className="actions-inline">
          <button className="btn primary" onClick={submit} disabled={!output.trim()}>添加</button>
          <button className="btn" onClick={onClose}>取消</button>
        </div>
      </div>
    </Modal>
  )
}
