import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { Report, ReportListItem } from '../api/types'
import { DimensionChart } from '../components/DimensionChart'
import { Modal } from '../components/Modal'
import { ScoreCard } from '../components/ScoreCard'
import { useAppStore } from '../stores/appStore'

export function ReportsPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [query, setQuery] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [showCompare, setShowCompare] = useState(false)
  const [comparison, setComparison] = useState<any>(null)

  const selectedReports = useAppStore((s) => s.selectedReports)
  const toggleReport = useAppStore((s) => s.toggleReport)

  async function loadReports() {
    setReports(await api.reports())
  }

  useEffect(() => { loadReports().catch(console.error) }, [])

  useEffect(() => {
    if (reportId) {
      api.report(reportId).then(setReport).catch(console.error)
    } else {
      setReport(null)
    }
  }, [reportId])

  useEffect(() => {
    if (showCompare && selectedReports.length >= 2) {
      api.compareReports(selectedReports).then(setComparison).catch(console.error)
    }
  }, [showCompare, selectedReports])

  const filtered = useMemo(
    () => reports.filter((r) => r.run_id.includes(query) || r.agent_name.includes(query)),
    [reports, query],
  )

  async function remove(runId: string) {
    await api.deleteReport(runId)
    await loadReports()
    if (reportId === runId) navigate('/reports')
  }

  const tasks = report ? Object.entries(report.task_results).flatMap(([plugin, items]) => items.map((item) => ({ plugin, ...item }))) : []
  const scoreData = comparison ? Object.entries(comparison.overall_scores).map(([run_id, score]) => ({ run_id, score })) : []

  // Detail view
  if (reportId && report) {
    return (
      <section>
        <div className="page-header">
          <div>
            <h2>报告详情</h2>
            <code>{report.run_id}</code>
          </div>
          <button onClick={() => navigate('/reports')}>← 返回列表</button>
        </div>
        <div className="cards">
          <ScoreCard title="Overall" value={report.summary.overall_score} />
          <ScoreCard title="Macro" value={report.summary.macro_score} />
          <ScoreCard title="Micro" value={report.summary.micro_score} />
          <ScoreCard title="Pass Rate" value={report.summary.pass_rate ? report.summary.pass_rate * 100 : 0} suffix="%" />
        </div>
        <div className="card"><h3>维度分数</h3><DimensionChart dimensions={report.summary.dimensions} /></div>
        <div className="card">
          <h3>插件结果</h3>
          <table>
            <thead><tr><th>插件</th><th>类型</th><th>分数</th><th>通过</th><th>失败</th><th>总数</th></tr></thead>
            <tbody>
              {Object.entries(report.plugin_results).map(([name, result]) => (
                <tr key={name}><td>{name}</td><td>{result.type}</td><td>{result.score?.toFixed?.(3) ?? '-'}</td><td>{result.passed}</td><td>{result.failed}</td><td>{result.total}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>任务结果</h3>
          <table>
            <thead><tr><th>插件</th><th>任务</th><th>分数</th><th>通过</th><th>耗时</th><th>错误</th></tr></thead>
            <tbody>
              {tasks.map((task, index) => (
                <tr key={`${task.plugin}-${task.task_id}-${index}`}>
                  <td>{task.plugin}</td>
                  <td>{task.task_id}</td>
                  <td>{task.score?.toFixed?.(3) ?? '-'}</td>
                  <td>{String(task.passed)}</td>
                  <td>{task.execution_time_ms}</td>
                  <td>{task.error || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )
  }

  // List view
  return (
    <section>
      <div className="page-header">
        <h2>报告</h2>
        <input className="search-input" placeholder="搜索 run_id 或 agent" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="actions-inline">
          <span className="muted">{selectedReports.length} 个已选</span>
          <button disabled={selectedReports.length < 2} onClick={() => setShowCompare(true)}>对比已选</button>
        </div>
      </div>
      <div className="card">
        {filtered.length === 0 ? <p className="muted empty-hint">暂无报告</p> : (
          <table>
            <thead><tr><th>选择</th><th>Run ID</th><th>Agent</th><th>时间</th><th>分数</th><th>操作</th></tr></thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.run_id}>
                  <td><input type="checkbox" checked={selectedReports.includes(r.run_id)} onChange={() => toggleReport(r.run_id)} /></td>
                  <td><code>{r.run_id}</code></td>
                  <td>{r.agent_name}</td>
                  <td>{r.timestamp}</td>
                  <td>{r.overall_score?.toFixed(3) ?? '-'}</td>
                  <td className="actions-inline">
                    <button onClick={() => navigate(`/reports/${r.run_id}`)}>详情</button>
                    <button className="danger" onClick={() => remove(r.run_id)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={showCompare} title={`报告对比（${selectedReports.length} 个）`} onClose={() => setShowCompare(false)} width="900px">
        {scoreData.length ? (
          <>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={scoreData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="run_id" hide />
                <YAxis domain={[0, 1]} />
                <Tooltip />
                <Legend />
                <Bar dataKey="score" fill="var(--accent)" />
              </BarChart>
            </ResponsiveContainer>
            <pre className="json-preview">{JSON.stringify(comparison?.comparison, null, 2)}</pre>
          </>
        ) : <p className="muted">请选择至少两个报告。</p>}
      </Modal>
    </section>
  )
}