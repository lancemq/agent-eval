import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ScorerInfo } from '../api/types'

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
  const [id, setId] = useState('qa_basic')
  const [name, setName] = useState('Basic QA Evaluation')
  const [dimensions, setDimensions] = useState('correctness')
  const [tasksText, setTasksText] = useState(JSON.stringify(defaultTasks, null, 2))
  const [template, setTemplate] = useState('Answer the following question concisely.\n\nQuestion: {input}')
  const [scorerType, setScorerType] = useState('exact_match')
  const [scorerParams, setScorerParams] = useState(JSON.stringify({ case_sensitive: false, strip: true }, null, 2))
  const [threshold, setThreshold] = useState(0.7)
  const [aggregation, setAggregation] = useState('weighted')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.scorers().then(setScorers).catch(console.error)
  }, [])

  function apply() {
    try {
      const tasks = JSON.parse(tasksText)
      const params = JSON.parse(scorerParams || '{}')
      const nextConfig = structuredClone(config || {})
      nextConfig.plugins = nextConfig.plugins || {}
      if (!enabled) {
        delete nextConfig.plugins.custom_eval
      } else {
        nextConfig.plugins.custom_eval = {
          enabled: true,
          evaluations: [
            {
              id,
              name,
              dimensions: dimensions.split(',').map((item) => item.trim()).filter(Boolean),
              task_source: { type: 'inline', items: tasks },
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
      <label>维度，逗号分隔</label>
      <input value={dimensions} onChange={(event) => setDimensions(event.target.value)} />
      <label>任务数据 JSON</label>
      <textarea className="compact-textarea" value={tasksText} onChange={(event) => setTasksText(event.target.value)} />
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
