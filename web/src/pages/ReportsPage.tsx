import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { ComparisonStatistics, Report, ReportListItem, RowLevelComparison } from '../api/types'
import { DimensionChart } from '../components/DimensionChart'
import { Modal } from '../components/Modal'
import { ScoreCard } from '../components/ScoreCard'
import { useAppStore } from '../stores/appStore'

type ComparisonResult = {
  reports: any[]
  comparison: any
  overall_scores: Record<string, number>
  pass_rates: Record<string, number>
  row_level: RowLevelComparison
  statistics: ComparisonStatistics
}

export function ReportsPage() {
  const { reportId } = useParams()
  const navigate = useNavigate()
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [query, setQuery] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [showCompare, setShowCompare] = useState(false)
  const [comparison, setComparison] = useState<ComparisonResult | null>(null)

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

  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  async function exportCsv(runId: string) {
    try {
      const blob = await api.exportReportCsv(runId)
      downloadBlob(blob, `${runId}.csv`)
    } catch (e) {
      alert(e instanceof Error ? e.message : '导出失败')
    }
  }

  async function exportComparisonCsv() {
    if (selectedReports.length < 2) return
    try {
      const blob = await api.exportComparisonCsv(selectedReports)
      downloadBlob(blob, `comparison_${selectedReports.slice(0, 3).join('_')}.csv`)
    } catch (e) {
      alert(e instanceof Error ? e.message : '导出失败')
    }
  }

  const tasks = report ? Object.entries(report.task_results).flatMap(([evaluator, items]) => items.map((item) => ({ evaluator, ...item }))) : []
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
          <div className="actions-inline">
            <button onClick={() => exportCsv(report.run_id)}>导出 CSV</button>
            <button onClick={() => navigate('/reports')}>← 返回列表</button>
          </div>
        </div>
        <div className="cards">
          <ScoreCard title="Overall" value={report.summary.overall_score} />
          <ScoreCard title="Macro" value={report.summary.macro_score} />
          <ScoreCard title="Micro" value={report.summary.micro_score} />
          <ScoreCard title="Pass Rate" value={report.summary.pass_rate ? report.summary.pass_rate * 100 : 0} suffix="%" />
        </div>
        <div className="card"><h3>指标分数</h3><DimensionChart dimensions={report.summary.dimensions} /></div>
        <div className="card">
          <h3>评估器结果</h3>
          <table>
            <thead><tr><th>评估器</th><th>类型</th><th>分数</th><th>通过</th><th>失败</th><th>总数</th></tr></thead>
            <tbody>
              {Object.entries(report.evaluator_results).map(([name, result]) => (
                <tr key={name}><td>{name}</td><td>{result.type}</td><td>{result.score?.toFixed?.(3) ?? '-'}</td><td>{result.passed}</td><td>{result.failed}</td><td>{result.total}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>任务结果</h3>
          <table>
            <thead><tr><th>评估器</th><th>任务</th><th>分数</th><th>通过</th><th>耗时</th><th>错误</th></tr></thead>
            <tbody>
              {tasks.map((task, index) => (
                <tr key={`${task.evaluator}-${task.task_id}-${index}`}>
                  <td>{task.evaluator}</td>
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
            <thead><tr><th>选择</th><th>实验 ID</th><th>Agent</th><th>时间</th><th>分数</th><th>操作</th></tr></thead>
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
                    <button onClick={() => exportCsv(r.run_id)}>CSV</button>
                    <button className="danger" onClick={() => remove(r.run_id)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={showCompare} title={`报告对比（${selectedReports.length} 个）`} onClose={() => setShowCompare(false)} width="960px">
        <div className="actions-inline" style={{ marginBottom: 8 }}>
          <button onClick={exportComparisonCsv}>导出对比 CSV</button>
        </div>
        {scoreData.length ? (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={scoreData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="run_id" hide />
                <YAxis domain={[0, 1]} />
                <Tooltip />
                <Legend />
                <Bar dataKey="score" fill="var(--accent)" />
              </BarChart>
            </ResponsiveContainer>

            {comparison?.statistics && (
              <div className="card" style={{ marginTop: 12 }}>
                <h3 className="section-title">统计显著性（Bootstrap 95% CI）</h3>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: 6 }}>报告</th>
                      <th style={{ textAlign: 'left', padding: 6 }}>均值</th>
                      <th style={{ textAlign: 'left', padding: 6 }}>95% CI</th>
                      <th style={{ textAlign: 'left', padding: 6 }}>样本数</th>
                      <th style={{ textAlign: 'left', padding: 6 }}>vs 基准 Δ</th>
                      <th style={{ textAlign: 'left', padding: 6 }}>显著性</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(comparison.statistics.ci).map(([rid, ciVal]) => {
                      const ci = ciVal as { mean: number; ci_low: number; ci_high: number; n: number }
                      const paired = comparison.statistics!.paired_vs_baseline
                      const isBaseline = rid === paired.baseline
                      const pr = paired.results[rid]
                      return (
                        <tr key={rid}>
                          <td style={{ padding: 6 }}><code>{rid.slice(0, 8)}</code>{isBaseline && <span className="muted"> (基准)</span>}</td>
                          <td style={{ padding: 6 }}>{ci.mean.toFixed(3)}</td>
                          <td style={{ padding: 6 }}>[{ci.ci_low.toFixed(3)}, {ci.ci_high.toFixed(3)}]</td>
                          <td style={{ padding: 6 }}>{ci.n}</td>
                          <td style={{ padding: 6 }}>{pr ? `${pr.mean_delta >= 0 ? '+' : ''}${pr.mean_delta.toFixed(3)}` : '—'}</td>
                          <td style={{ padding: 6 }}>
                            {pr ? (
                              pr.significant ? (
                                <span style={{ color: pr.mean_delta > 0 ? 'var(--success, #27ae60)' : 'var(--danger, #c0392b)' }}>
                                  {pr.mean_delta > 0 ? '显著优于基准' : '显著劣于基准'} (p≈{pr.p_value_approx})
                                </span>
                              ) : <span className="muted">无显著差异 (p≈{pr.p_value_approx})</span>
                            ) : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {comparison?.row_level && comparison.row_level.aligned_rows.length > 0 && (
              <div className="card" style={{ marginTop: 12 }}>
                <h3 className="section-title">
                  行级 Diff（对齐 {comparison.row_level.summary.aligned} 行 · 新增 {comparison.row_level.summary.added} · 移除 {comparison.row_level.summary.removed}）
                </h3>
                <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left', padding: 6 }}>评估器</th>
                        <th style={{ textAlign: 'left', padding: 6 }}>task_id</th>
                        {comparison.row_level.labels.map((l) => (
                          <th key={l} style={{ textAlign: 'left', padding: 6 }}>{l.slice(0, 8)} 分数</th>
                        ))}
                        <th style={{ textAlign: 'left', padding: 6 }}>Δ(基准→其它)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.row_level.aligned_rows.map((row, i) => {
                        const deltaVals: number[] = Object.values(row.score_deltas || {}) as number[]
                        const maxDelta = deltaVals.length ? Math.max(...deltaVals.map((x) => Math.abs(x))) : 0
                        return (
                          <tr key={`${row.evaluator}-${row.task_id}-${i}`}>
                            <td style={{ padding: 6 }}>{row.evaluator}</td>
                            <td style={{ padding: 6 }}><code>{row.task_id}</code></td>
                            {comparison.row_level!.labels.map((l) => {
                              const s = row.scores[l]
                              return <td key={l} style={{ padding: 6 }}>{s != null ? s.toFixed(3) : '—'}</td>
                            })}
                            <td style={{ padding: 6 }}>
                              {deltaVals.map((d: number, idx) => (
                                <span key={idx} style={{ color: d > 0 ? 'var(--success, #27ae60)' : d < 0 ? 'var(--danger, #c0392b)' : 'inherit', marginRight: 6 }}>
                                  {d >= 0 ? '+' : ''}{d.toFixed(3)}
                                </span>
                              ))}
                              {maxDelta === 0 && <span className="muted">无变化</span>}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <pre className="json-preview">{JSON.stringify(comparison?.comparison, null, 2)}</pre>
          </>
        ) : <p className="muted">请选择至少两个报告。</p>}
      </Modal>
    </section>
  )
}