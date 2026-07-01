import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export function CreateDatasetPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [rowsText, setRowsText] = useState('[\n  {"task_id": "t1", "input": "你好", "expected": "hello"}\n]')
  const [error, setError] = useState('')

  async function submit() {
    let rows: any[]
    try {
      rows = JSON.parse(rowsText)
      if (!Array.isArray(rows)) throw new Error('行数据必须是数组')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'JSON 解析失败')
      return
    }
    try {
      await api.createDataset({ name, rows, description })
      navigate('/datasets', { state: { select: name } })
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败')
    }
  }

  return (
    <section>
      <div className="page-header">
        <h2>新建数据集</h2>
        <div className="actions-inline">
          <button className="btn" onClick={() => navigate('/datasets')}>返回</button>
        </div>
      </div>
      {error && <p className="message">{error}</p>}
      <div className="card form">
        <label>名称</label>
        <input className="search-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="my_dataset" />
        <label>描述</label>
        <input className="search-input" value={description} onChange={(e) => setDescription(e.target.value)} />
        <label>行数据（JSON 数组）</label>
        <textarea className="compact-textarea" rows={8} value={rowsText} onChange={(e) => setRowsText(e.target.value)} style={{ fontFamily: 'monospace' }} />
        <div className="actions-inline">
          <button className="btn primary" onClick={submit} disabled={!name}>创建</button>
          <button className="btn" onClick={() => navigate('/datasets')}>取消</button>
        </div>
      </div>
    </section>
  )
}
