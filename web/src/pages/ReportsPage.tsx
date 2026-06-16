import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ReportListItem } from '../api/types'

export function ReportsPage({ setPage, setActiveReportId, selectedReports, setSelectedReports }: { setPage: (page: string) => void; setActiveReportId: (id: string) => void; selectedReports: string[]; setSelectedReports: (ids: string[]) => void }) {
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [query, setQuery] = useState('')

  async function load() {
    setReports(await api.reports())
  }

  useEffect(() => { load().catch(console.error) }, [])

  async function remove(runId: string) {
    await api.deleteReport(runId)
    await load()
  }

  function toggleCompare(runId: string) {
    setSelectedReports(selectedReports.includes(runId) ? selectedReports.filter((id) => id !== runId) : [...selectedReports, runId])
  }

  const filtered = reports.filter((report) => report.run_id.includes(query) || report.agent_name.includes(query))

  return (
    <section>
      <div className="page-header"><h2>报告列表</h2><button onClick={() => setPage('compare')}>对比已选</button></div>
      <div className="card">
        <input placeholder="搜索 run_id 或 agent" value={query} onChange={(event) => setQuery(event.target.value)} />
        <table>
          <thead><tr><th>选择</th><th>Run ID</th><th>Agent</th><th>时间</th><th>分数</th><th>操作</th></tr></thead>
          <tbody>
            {filtered.map((report) => (
              <tr key={report.run_id}>
                <td><input type="checkbox" checked={selectedReports.includes(report.run_id)} onChange={() => toggleCompare(report.run_id)} /></td>
                <td><code>{report.run_id}</code></td>
                <td>{report.agent_name}</td>
                <td>{report.timestamp}</td>
                <td>{report.overall_score?.toFixed(3) ?? '-'}</td>
                <td className="actions-inline">
                  <button onClick={() => { setActiveReportId(report.run_id); setPage('report-detail') }}>详情</button>
                  <button className="danger" onClick={() => remove(report.run_id)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
