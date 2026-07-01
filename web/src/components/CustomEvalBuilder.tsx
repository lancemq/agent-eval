import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DatasetSummary, ScorerInfo } from '../api/types'

type Props = {
  config: any
  onApply: (config: any) => void
}

const defaultTasks = [
  { task_id: 'q1', input: 'What is the capital of France?', expected: 'Paris' },
  { task_id: 'q2', input: '2 + 2 = ?', expected: '4' },
]

export function CustomEvalBuilder({ config, onApply }: Props) {
  const [enabled, setEnabled] = useState(true)
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [id, setId] = useState('qa_basic')
  const [name, setName] = useState('Basic QA Evaluation')
  const [dimensions, setDimensions] = useState('correctness')
  const [taskSourceMode, setTaskSourceMode] = useState<'inline' | 'dataset'>('inline')
  const [tasksText, setTasksText] = useState(JSON.stringify(defaultTasks, null, 2))
  const [datasetName, setDatasetName] = useState('')
  const [datasetVersion, setDatasetVersion] = useState('')
  const [template, setTemplate] = useState('Answer the following question concisely.\n\nQuestion: {input}')
  const [scorerType, setScorerType] = useState('exact_match')
  const [scorerParams, setScorerParams] = useState(JSON.stringify({ case_sensitive: false, strip: true }, null, 2))
  const [threshold, setThreshold] = useState(0.7)
  const [aggregation, setAggregation] = useState('weighted')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.scorers().then(setScorers).catch(console.error)
    api.datasets().then(setDatasets).catch(console.error)
  }, [])

  function apply() {
    try {
      const params = JSON.parse(scorerParams || '{}')
      const taskSource = taskSourceMode === 'inline'
        ? { type: 'inline', items: JSON.parse(tasksText) }
        : { type: 'dataset', name: datasetName, ...(datasetVersion ? { version: datasetVersion } : {}) }
      const nextConfig = structuredClone(config || {})
      nextConfig.evaluators = nextConfig.evaluators || {}
      if (!enabled) {
        delete nextConfig.evaluators.custom_eval
      } else {
        nextConfig.evaluators.custom_eval = {
          enabled: true,
          evaluations: [
            {
              id,
              name,
              dimensions: dimensions.split(',').map((item) => item.trim()).filter(Boolean),
              task_source: taskSource,
              prompt: { mode: 'generate', template },
              scoring: {
                threshold,
                aggregation,
                scorers: [
                  {
                    id: scorerType,
                    type: scorerType,
                    weight: 1,
                    dimension: dimensions.split(',').map((item) => item.trim()).filter(Boolean)[0] || 'custom',
                    params,
                  },
                ],
              },
            },
          ],
        }
      }
      onApply(nextConfig)
      setMessage(enabled ? '已应用 custom_eval 配置' : '已移除 custom_eval 配置')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '配置解析失败')
    }
  }

  return (
    <div className="card form custom-eval-builder">
      <div className="section-title">
        <div>
          <h3>自定义评测方式</h3>
          <p className="muted">无需写 Python，直接定义任务、Prompt 和评分方式。</p>
        </div>
        <label className="switch-row"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用</label>
      </div>

      <label>评测 ID</label>
      <input value={id} onChange={(event) => setId(event.target.value)} />
      <label>展示名称</label>
      <input value={name} onChange={(event) => setName(event.target.value)} />
      <label>指标，逗号分隔</label>
      <input value={dimensions} onChange={(event) => setDimensions(event.target.value)} />

      <label>任务来源</label>
      <div className="actions-inline">
        <label className="switch-row"><input type="radio" checked={taskSourceMode === 'inline'} onChange={() => setTaskSourceMode('inline')} />内联 JSON</label>
        <label className="switch-row"><input type="radio" checked={taskSourceMode === 'dataset'} onChange={() => setTaskSourceMode('dataset')} />引用数据集</label>
        <Link to="/datasets" className="muted" style={{ marginLeft: 'auto' }}>管理数据集 →</Link>
      </div>
      {taskSourceMode === 'inline' ? (
        <>
          <label>任务数据 JSON</label>
          <textarea className="compact-textarea" value={tasksText} onChange={(event) => setTasksText(event.target.value)} />
        </>
      ) : (
        <div className="two-field-row">
          <div>
            <label>数据集名称</label>
            <select value={datasetName} onChange={(event) => { setDatasetName(event.target.value); setDatasetVersion('') }}>
              <option value="">请选择...</option>
              {datasets.map((ds) => <option key={ds.name} value={ds.name}>{ds.name} (v{ds.latest_version}, {ds.row_count}行)</option>)}
            </select>
          </div>
          <div>
            <label>版本（可选，默认最新）</label>
            <input value={datasetVersion} onChange={(event) => setDatasetVersion(event.target.value)} placeholder="留空用最新" />
          </div>
        </div>
      )}

      <label>Prompt 模板</label>
      <textarea className="compact-textarea" value={template} onChange={(event) => setTemplate(event.target.value)} />
      <label>评分器</label>
      <select value={scorerType} onChange={(event) => setScorerType(event.target.value)}>
        {scorers.map((scorer) => <option key={scorer.type} value={scorer.type}>{scorer.type} - {scorer.description}</option>)}
      </select>
      <div className="two-field-row">
        <div>
          <label>通过阈值</label>
          <input type="number" min="0" max="1" step="0.05" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
        </div>
        <div>
          <label>聚合方式</label>
          <select value={aggregation} onChange={(event) => setAggregation(event.target.value)}>
            <option value="weighted">weighted</option>
            <option value="mean">mean</option>
            <option value="median">median</option>
            <option value="min">min</option>
            <option value="max">max</option>
          </select>
        </div>
      </div>
      <label>评分器参数 JSON</label>
      <textarea className="compact-textarea" value={scorerParams} onChange={(event) => setScorerParams(event.target.value)} />
      <button type="button" className="primary" onClick={apply}>应用到配置 JSON</button>
      {message && <p className="message">{message}</p>}
    </div>
  )
}
