import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PluginInfo, ReportListItem } from '../api/types'
import { ScoreCard } from '../components/ScoreCard'

export function DashboardPage({ setPage }: { setPage: (page: string) => void }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [reports, setReports] = useState<ReportListItem[]>([])

  useEffect(() => {
    api.plugins().then(setPlugins).catch(console.error)
    api.reports().then(setReports).catch(console.error)
  }, [])

  const latest = reports[0]
  const byType = plugins.reduce<Record<string, number>>((acc, plugin) => {
    acc[plugin.type] = (acc[plugin.type] || 0) + 1
    return acc
  }, {})

  return (
    <section>
      <div className="page-header">
        <h2>评测总览</h2>
        <button onClick={() => setPage('run')}>新建评测</button>
      </div>
      <div className="cards">
        <ScoreCard title="最近分数" value={latest?.overall_score} />
        <ScoreCard title="历史报告" value={reports.length} />
        <ScoreCard title="可用插件" value={plugins.length} />
        <ScoreCard title="Benchmark 插件" value={byType.benchmark || 0} />
      </div>
      <div className="card">
        <h3>关键流程</h3>
        <div className="actions-inline">
          <button className="primary" onClick={() => setPage('traces')}>基于 Trace 创建 Eval</button>
          <button onClick={() => setPage('scorers')}>查看 Scorer</button>
          <button onClick={() => setPage('plugins')}>查看插件</button>
          <button onClick={() => setPage('settings')}>配置中心</button>
          <button onClick={() => setPage('reports')}>查看报告</button>
        </div>
      </div>
      <div className="card">
        <h3>最近报告</h3>
        {reports.slice(0, 6).map((report) => (
          <div className="list-row" key={report.run_id}>
            <span>{report.run_id}</span>
            <strong>{report.overall_score?.toFixed(3) ?? '-'}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
