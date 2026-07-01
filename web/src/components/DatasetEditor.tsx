import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DatasetDetail, DatasetDiff, DatasetRow } from '../api/types'

type Props = {
  name: string
  onBack: () => void
}

const STANDARD_FIELDS = ['task_id', 'input', 'expected']

export function DatasetEditor({ name, onBack }: Props) {
  const [detail, setDetail] = useState<DatasetDetail | null>(null)
  const [rows, setRows] = useState<DatasetRow[]>([])
  const [dirty, setDirty] = useState(false)
  const [message, setMessage] = useState('')
  const [extraFields, setExtraFields] = useState<string[]>([])
  const [diff, setDiff] = useState<DatasetDiff | null>(null)
  const [diffVersions, setDiffVersions] = useState<{ v1: string; v2: string }>({ v1: '', v2: '' })
  const [showDiff, setShowDiff] = useState(false)

  useEffect(() => {
    api.dataset(name).then((d) => {
      setDetail(d)
      setRows(d.rows.map((r) => ({ ...r })))
      setExtraFields(computeExtraFields(d.rows))
      setDirty(false)
    }).catch((e) => setMessage(e instanceof Error ? e.message : '加载失败'))
  }, [name])

  function computeExtraFields(rs: DatasetRow[]): string[] {
    const fields = new Set<string>()
    rs.forEach((r) => Object.keys(r).forEach((k) => fields.add(k)))
    return [...fields].filter((f) => !STANDARD_FIELDS.includes(f))
  }

  function updateField(idx: number, field: string, value: any) {
    setRows((prev) => {
      const next = prev.map((r) => ({ ...r }))
      next[idx] = { ...next[idx], [field]: value }
      return next
    })
    setDirty(true)
  }

  function addRow() {
    setRows((prev) => [...prev, { task_id: `task_${prev.length + 1}`, input: '', expected: '' }])
    setDirty(true)
  }

  function duplicateRow(idx: number) {
    setRows((prev) => {
      const copy = { ...prev[idx], task_id: `${prev[idx].task_id}_copy` }
      const next = [...prev]
      next.splice(idx + 1, 0, copy)
      return next
    })
    setDirty(true)
  }

  function removeRow(idx: number) {
    setRows((prev) => prev.filter((_, i) => i !== idx))
    setDirty(true)
  }

  function addField() {
    const name = window.prompt('新字段名')
    if (!name) return
    setExtraFields((prev) => prev.includes(name) ? prev : [...prev, name])
  }

  async function save() {
    if (!detail) return
    try {
      await api.updateDatasetRows(name, rows)
      setMessage('已保存（新 patch 版本）')
      setDirty(false)
      const d = await api.dataset(name)
      setDetail(d)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '保存失败')
    }
  }

  async function saveAsVersion() {
    if (!detail) return
    const desc = window.prompt('新版本说明', '') || ''
    try {
      await api.addDatasetVersion(name, { rows, description: desc })
      setMessage('已创建新版本')
      setDirty(false)
      const d = await api.dataset(name)
      setDetail(d)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '创建失败')
    }
  }

  async function loadVersion(version: string) {
    if (!version) return
    const d = await api.dataset(name, version)
    setDetail(d)
    setRows(d.rows.map((r) => ({ ...r })))
    setExtraFields(computeExtraFields(d.rows))
    setDirty(false)
    setMessage(`已切换到版本 ${version}`)
  }

  async function runDiff() {
    if (!diffVersions.v1 || !diffVersions.v2 || diffVersions.v1 === diffVersions.v2) return
    const d = await api.diffDataset(name, diffVersions.v1, diffVersions.v2)
    setDiff(d)
    setShowDiff(true)
  }

  async function removeFromStore() {
    if (!window.confirm(`确认删除数据集 "${name}" 及其所有版本？`)) return
    await api.deleteDataset(name)
    onBack()
  }

  if (!detail) {
    return <section><div className="card"><p className="muted">加载中...</p>{message && <p className="message">{message}</p>}</div></section>
  }

  const allFields = [...STANDARD_FIELDS, ...extraFields]

  return (
    <section>
      <div className="page-header">
        <button className="btn" onClick={onBack}>← 返回列表</button>
        <h2>数据集：{name}</h2>
        <div className="actions-inline">
          <select value="" onChange={(e) => loadVersion(e.target.value)} className="search-input">
            <option value="">版本：{detail.version}（共 {detail.versions.length} 个）</option>
            {detail.versions.slice().reverse().map((v) => (
              <option key={v.version} value={v.version}>v{v.version} · {v.row_count} 行 · {v.updated_at.slice(0, 10)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="card">
        <div className="actions-inline">
          <button className="btn primary" onClick={save} disabled={!dirty}>保存（patch 版本）</button>
          <button className="btn" onClick={saveAsVersion}>另存为新版本</button>
          <button className="btn" onClick={addRow}>+ 新增行</button>
          <button className="btn" onClick={addField}>+ 新增字段</button>
          <span className="muted">当前版本 v{detail.version} · {rows.length} 行</span>
          <button className="btn danger" onClick={removeFromStore} style={{ marginLeft: 'auto' }}>删除数据集</button>
        </div>
        {message && <p className="message">{message}</p>}

        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {allFields.map((f) => (
                  <th key={f} style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid var(--border)' }}>{f}</th>
                ))}
                <th style={{ width: 90 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx}>
                  {allFields.map((f) => (
                    <td key={f} style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                      <input
                        value={typeof row[f] === 'object' ? JSON.stringify(row[f]) : String(row[f] ?? '')}
                        onChange={(e) => updateField(idx, f, e.target.value)}
                        style={{ width: '100%', boxSizing: 'border-box', background: 'transparent', border: '1px solid transparent', borderRadius: 4, padding: '2px 4px' }}
                      />
                    </td>
                  ))}
                  <td>
                    <button className="btn" onClick={() => duplicateRow(idx)} title="复制行">⎘</button>
                    <button className="btn danger" onClick={() => removeRow(idx)} title="删除行">✕</button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={allFields.length + 1} className="muted" style={{ padding: 16, textAlign: 'center' }}>暂无数据行，点击 "+ 新增行" 添加</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3 className="section-title">版本对比</h3>
        <div className="actions-inline">
          <select value={diffVersions.v1} onChange={(e) => setDiffVersions((v) => ({ ...v, v1: e.target.value }))} className="search-input">
            <option value="">版本 A</option>
            {detail.versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
          </select>
          <select value={diffVersions.v2} onChange={(e) => setDiffVersions((v) => ({ ...v, v2: e.target.value }))} className="search-input">
            <option value="">版本 B</option>
            {detail.versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
          </select>
          <button className="btn primary" onClick={runDiff} disabled={!diffVersions.v1 || !diffVersions.v2 || diffVersions.v1 === diffVersions.v2}>生成 Diff</button>
        </div>

        {showDiff && diff && (
          <div style={{ marginTop: 12 }}>
            <div className="actions-inline">
              <span className="muted">新增 {diff.summary.added}</span>
              <span className="muted">删除 {diff.summary.removed}</span>
              <span className="muted">修改 {diff.summary.modified}</span>
              <span className="muted">未变 {diff.summary.unchanged}</span>
            </div>
            {diff.modified.length > 0 && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginTop: 8 }}>
                <thead><tr><th style={{ textAlign: 'left', padding: 6 }}>task_id</th><th style={{ textAlign: 'left', padding: 6 }}>字段</th><th style={{ textAlign: 'left', padding: 6 }}>原值</th><th style={{ textAlign: 'left', padding: 6 }}>新值</th></tr></thead>
                <tbody>
                  {diff.modified.flatMap((m) => Object.entries(m.fields).map(([field, ch]) => (
                    <tr key={`${m.task_id}-${field}`}>
                      <td style={{ padding: 6 }}>{m.task_id}</td>
                      <td style={{ padding: 6 }}>{field}</td>
                      <td style={{ padding: 6, color: 'var(--danger, #c0392b)' }}>{JSON.stringify(ch.from)}</td>
                      <td style={{ padding: 6, color: 'var(--success, #27ae60)' }}>{JSON.stringify(ch.to)}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            )}
            {diff.added.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong className="muted">新增行（{diff.added.length}）：</strong>
                <pre className="json-preview">{JSON.stringify(diff.added, null, 2)}</pre>
              </div>
            )}
            {diff.removed.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong className="muted">删除行（{diff.removed.length}）：</strong>
                <pre className="json-preview">{JSON.stringify(diff.removed, null, 2)}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
