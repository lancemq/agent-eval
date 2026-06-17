import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PluginInfo, ReportListItem } from '../api/types'

type Props = {
  setPage: (page: string) => void
  onNewRun: () => void
  onOpenWizard: () => void
}

export function DashboardPage({ setPage, onNewRun, onOpenWizard }: Props) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [scorerCount, setScorerCount] = useState(0)

  useEffect(() => {
    api.plugins().then(setPlugins).catch(console.error)
    api.reports().then(setReports).catch(console.error)
    api.scorers().then((items) => setScorerCount(items.length)).catch(console.error)
  }, [])

  const latest = reports[0]
  const byType = plugins.reduce<Record<string, number>>((acc, plugin) => {
    acc[plugin.type] = (acc[plugin.type] || 0) + 1
    return acc
  }, {})

  return (
    <section className="dashboard">
      <div className="hero">
        <div className="hero-text">
          <h2>评测总览</h2>
          <p>快速发起、监控和分析你的 Agent 评测</p>
        </div>
        <button className="primary hero-cta" onClick={onNewRun}>+ 新建评测</button>
      </div>

      <div className="metric-row">
        <div className="metric" style={{ animationDelay: '0ms' }}>
          <span className="metric-label">最近分数</span>
          <strong className="metric-value">{latest?.overall_score?.toFixed(3) ?? '—'}</strong>
        </div>
        <div className="metric" style={{ animationDelay: '60ms' }}>
          <span className="metric-label">历史报告</span>
          <strong className="metric-value">{reports.length}</strong>
        </div>
        <div className="metric" style={{ animationDelay: '120ms' }}>
          <span className="metric-label">可用插件</span>
          <strong className="metric-value">{plugins.length}</strong>
        </div>
        <div className="metric" style={{ animationDelay: '180ms' }}>
          <span className="metric-label">Scorer</span>
          <strong className="metric-value">{scorerCount}</strong>
        </div>
      </div>

      <div className="dash-grid">
        <div className="card dash-card">
          <h3>最近评测</h3>
          {reports.length === 0 ? (
            <p className="muted empty-hint">暂无报告，点击「新建评测」开始</p>
          ) : (
            reports.slice(0, 6).map((report) => (
              <div className="report-item" key={report.run_id} onClick={() => setPage('runs')}>
                <div className="report-item-main">
                  <code>{report.run_id}</code>
                  <small className="muted">{report.agent_name}</small>
                </div>
                <strong className={report.overall_score !== undefined && report.overall_score >= 0.7 ? 'score-good' : 'score-low'}>
                  {report.overall_score?.toFixed(3) ?? '-'}
                </strong>
              </div>
            ))
          )}
        </div>

        <div className="card dash-card">
          <h3>插件分布</h3>
          {Object.entries(byType).length === 0 ? (
            <p className="muted empty-hint">加载中...</p>
          ) : (
            <div className="stat-list">
              {Object.entries(byType).map(([type, count]) => (
                <div className="stat-row" key={type}>
                  <span>{type}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>
          )}
          <h3 className="quick-title">快捷入口</h3>
          <div className="quick-links">
            <button className="quick-link" onClick={onOpenWizard}>Langfuse Trace 生成评测</button>
            <button className="quick-link" onClick={() => setPage('resources')}>资源中心</button>
            <button className="quick-link" onClick={() => setPage('runs')}>查看报告</button>
            <button className="quick-link" onClick={() => setPage('settings')}>配置中心</button>
          </div>
        </div>
      </div>
    </section>
  )
}
