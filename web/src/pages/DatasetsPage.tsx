import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { DatasetSummary, TraceSummary } from '../api/types'
import { DatasetEditor } from '../components/DatasetEditor'
import { Modal } from '../components/Modal'

export function DatasetsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)

  async function load() {
    try {
      setDatasets(await api.datasets())
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => {
    load()
    const state = location.state as { select?: string } | null
    if (state?.select) setSelected(state.select)
  }, [location])

  if (selected) {
    return <DatasetEditor name={selected} onBack={() => { setSelected(null); load() }} />
  }

  return (
    <section>
      <div className="page-header">
        <h2>评估用例数据集</h2>
        <div className="actions-inline">
          <button className="btn primary" onClick={() => navigate('/datasets/new')}>+ 新建数据集</button>
          <button className="btn" onClick={() => setShowImport(true)}>从 Trace 导入</button>
        </div>
      </div>
      {message && <p className="message">{message}</p>}

      <div className="cards">
        {datasets.map((ds) => (
          <div key={ds.name} className="card" style={{ cursor: 'pointer' }} onClick={() => setSelected(ds.name)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>{ds.name}</h3>
              <span className="muted">v{ds.latest_version}</span>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>{ds.description || '无描述'}</p>
            <div className="actions-inline">
              <span className="muted">{ds.row_count} 行</span>
              <span className="muted">{ds.version_count} 个版本</span>
              <span className="muted">更新于 {ds.updated_at.slice(0, 10)}</span>
            </div>
          </div>
        ))}
        {datasets.length === 0 && (
          <div className="card">
            <p className="muted empty-hint">暂无数据集。点击 "新建数据集" 手动创建，或 "从 Trace 导入" 从 Trace 生成评测用例。</p>
          </div>
        )}
      </div>

      {showImport && <ImportFromTracesModal open={showImport} onClose={() => setShowImport(false)} onImported={(name) => { setShowImport(false); setSelected(name) }} />}
    </section>
  )
}

function ImportFromTracesModal({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: (name: string) => void }) {
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.traces().then(setTraces).catch((e) => setError(e instanceof Error ? e.message : '加载 trace 失败'))
  }, [])

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function submit() {
    try {
      const result = await api.datasetFromTraces(name, {
        trace_ids: [...selected],
        description,
        create_new: true,
      })
      onImported(result.name)
    } catch (e) {
      setError(e instanceof Error ? e.message : '导入失败')
    }
  }

  return (
    <Modal open={open} title="从 Trace 导入数据集" onClose={onClose}>
      <div className="card form">
        <label>数据集名称</label>
        <input className="search-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="from_traces_v1" />
        <label>描述</label>
        <input className="search-input" value={description} onChange={(e) => setDescription(e.target.value)} />
        <label>选择 Trace（{selected.size} 已选 / {traces.length} 条）</label>
        <div style={{ maxHeight: 280, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
          {traces.map((t) => (
            <div key={t.trace_id} className="list-row" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 6 }}>
              <input type="checkbox" checked={selected.has(t.trace_id)} onChange={() => toggle(t.trace_id)} />
              <span style={{ flex: 1 }}>{t.trace_id}</span>
              <span className="muted">{t.trace_type}</span>
              <span className="muted">{t.success ? '✓' : '✕'}</span>
            </div>
          ))}
          {traces.length === 0 && <p className="muted" style={{ padding: 12 }}>暂无 trace 记录</p>}
        </div>
        {error && <p className="message">{error}</p>}
        <div className="actions-inline">
          <button className="btn primary" onClick={submit} disabled={!name || selected.size === 0}>导入（{selected.size} 条）</button>
          <button className="btn" onClick={onClose}>取消</button>
        </div>
      </div>
    </Modal>
  )
}
