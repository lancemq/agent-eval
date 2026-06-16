import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Report } from '../api/types'
import { DimensionChart } from '../components/DimensionChart'
import { ScoreCard } from '../components/ScoreCard'

export function ReportDetailPage({ activeReportId }: { activeReportId?: string }) {
  const [report, setReport] = useState<Report | null>(null)

  useEffect(() => {
    if (activeReportId) api.report(activeReportId).then(setReport).catch(console.error)
  }, [activeReportId])

  if (!activeReportId) return <div className="card"><h2>未选择报告</h2></div>
  if (!report) return <div className="card"><h2>加载中</h2></div>

  const tasks = Object.entries(report.task_results).flatMap(([plugin, items]) => items.map((item) => ({ plugin, ...item })))

  return (
    <section>
      <div className="page-header"><h2>报告详情</h2><code>{report.run_id}</code></div>
      <div className="cards">
        <ScoreCard title="Overall" value={report.summary.overall_score} />
        <ScoreCard title="Macro" value={report.summary.macro_score} />
        <ScoreCard title="Micro" value={report.summary.micro_score} />
        <ScoreCard title="Pass Rate" value={report.summary.pass_rate ? report.summary.pass_rate * 100 : 0} suffix="%" />
      </div>
      <div className="card"><h3>维度分数</h3><DimensionChart dimensions={report.summary.dimensions} /></div>
      <div className="card">
        <h3>插件结果</h3>
        <table><thead><tr><th>插件</th><th>类型</th><th>分数</th><th>通过</th><th>失败</th><th>总数</th></tr></thead><tbody>
          {Object.entries(report.plugin_results).map(([name, result]) => (
            <tr key={name}><td>{name}</td><td>{result.type}</td><td>{result.score?.toFixed?.(3) ?? '-'}</td><td>{result.passed}</td><td>{result.failed}</td><td>{result.total}</td></tr>
          ))}
        </tbody></table>
      </div>
      <div className="card">
        <h3>任务结果</h3>
        <table><thead><tr><th>插件</th><th>任务</th><th>分数</th><th>通过</th><th>耗时</th><th>错误</th></tr></thead><tbody>
          {tasks.map((task, index) => (
            <tr key={`${task.plugin}-${task.task_id}-${index}`}><td>{task.plugin}</td><td>{task.task_id}</td><td>{task.score?.toFixed?.(3) ?? '-'}</td><td>{String(task.passed)}</td><td>{task.execution_time_ms}</td><td>{task.error || '-'}</td></tr>
          ))}
        </tbody></table>
      </div>
    </section>
  )
}
