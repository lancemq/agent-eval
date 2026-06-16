import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { ReportListItem } from '../api/types'

export function ComparePage({ selectedReports, setSelectedReports }: { selectedReports: string[]; setSelectedReports: (ids: string[]) => void }) {
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [comparison, setComparison] = useState<any>(null)

  useEffect(() => { api.reports().then(setReports).catch(console.error) }, [])
  useEffect(() => {
    if (selectedReports.length >= 2) api.compareReports(selectedReports).then(setComparison).catch(console.error)
  }, [selectedReports])

  function toggle(runId: string) {
    setSelectedReports(selectedReports.includes(runId) ? selectedReports.filter((id) => id !== runId) : [...selectedReports, runId])
  }

  const scoreData = comparison ? Object.entries(comparison.overall_scores).map(([run_id, score]) => ({ run_id, score })) : []

  return (
    <section>
      <div className="page-header"><h2>报告对比</h2><span>{selectedReports.length} 个已选</span></div>
      <div className="two-column">
        <div className="card">
          <h3>选择报告</h3>
          {reports.map((report) => (
            <label key={report.run_id} className="check-row">
              <input type="checkbox" checked={selectedReports.includes(report.run_id)} onChange={() => toggle(report.run_id)} />
              <span>{report.run_id}</span>
            </label>
          ))}
        </div>
        <div className="card">
          <h3>Overall Score</h3>
          {scoreData.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={scoreData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="run_id" hide /><YAxis domain={[0, 1]} /><Tooltip /><Legend /><Bar dataKey="score" fill="#16a34a" /></BarChart>
            </ResponsiveContainer>
          ) : <p className="muted">请选择至少两个报告。</p>}
        </div>
      </div>
      {comparison && <pre className="card json-preview">{JSON.stringify(comparison.comparison, null, 2)}</pre>}
    </section>
  )
}
