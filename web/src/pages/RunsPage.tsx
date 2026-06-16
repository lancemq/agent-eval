import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { Report, ReportListItem, RunEvent, RunState } from '../api/types'
import { DimensionChart } from '../components/DimensionChart'
import { EventLog } from '../components/EventLog'
import { Modal } from '../components/Modal'
import { ScoreCard } from '../components/ScoreCard'

type Tab = 'list' | 'monitor' | 'detail'

type Props = {
  activeRunId?: string
  setActiveRunId: (id: string) => void
  activeReportId?: string
  setActiveReportId: (id: string) => void
  selectedReports: string[]
  setSelectedReports: (ids: string[]) => void
  initialTab?: Tab
}

export function RunsPage({ activeRunId, setActiveRunId, activeReportId, setActiveReportId, selectedReports, setSelectedReports, initialTab = 'list' }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab)
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [query, setQuery] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [run, setRun] = useState<RunState | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [showCompare, setShowCompare] = useState(false)
  const [comparison, setComparison] = useState<any>(null)

  async function loadReports() {
    setReports(await api.reports())
  }

  useEffect(() => { loadReports().catch(console.error) }, [])

  useEffect(() => {
    if (activeReportId) {
      setTab('detail')
      api.report(activeReportId).then(setReport).catch(console.error)
    }
  }, [activeReportId])

  useEffect(() => {
    if (!activeRunId) return
    setTab('monitor')
    let stopped = false
    const source = new EventSource(`/api/runs/${activeRunId}/events`)
    source.onmessage = (message) => setEvents((items) => [...items, JSON.parse(message.data)])
    const knownEvents = ['run_queued', 'evaluation_start', 'plugin_setup', 'task_generated', 'task_execute', 'task_evaluate', 'task_complete', 'task_failed', 'plugin_teardown', 'evaluation_complete', 'evaluation_failed']
    knownEvents.forEach((name) => source.addEventListener(name, (message) => setEvents((items) => [...items, JSON.parse((message as MessageEvent).data)])))
    const interval = window.setInterval(async () => {
      if (!stopped) setRun(await api.run(activeRunId))
    }, 1000)
    api.run(activeRunId).then(setRun).catch(console.error)
    return () => {
      stopped = true
      source.close()
      window.clearInterval(interval)
    }
  }, [activeRunId])

  useEffect(() => {
    if (showCompare && selectedReports.length >= 2) {
      api.compareReports(selectedReports).then(setComparison).catch(console.error)
    }
  }, [showCompare, selectedReports])

  const filtered = useMemo(() => reports.filter((r) => r.run_id.includes(query) || r.agent_name.includes(query)), [reports, query])

  function toggleCompare(runId: string) {
    setSelectedReports(selectedReports.includes(runId) ? selectedReports.filter((id) => id !== runId) : [...selectedReports, runId])
  }

  async function remove(runId: string) {
    await api.deleteReport(runId)
    await loadReports()
  }

  const progress = run?.progress
  const percent = progress && progress.total ? Math.round(((progress.completed + progress.failed) / progress.total) * 100) : 0
  const tasks = report ? Object.entries(report.task_results).flatMap(([plugin, items]) => items.map((item) => ({ plugin, ...item }))) : []
  const scoreData = comparison ? Object.entries(comparison.overall_scores).map(([run_id, score]) => ({ run_id, score })) : []

  return (
    <section>
      <div className="tab-bar">
        <button className={tab === 'list' ? 'tab active' : 'tab'} onClick={() => setTab('list')}>报告列表</button>
        <button className={tab === 'monitor' ? 'tab active' : 'tab'} onClick={() => setTab('monitor')}>运行监控 {activeRunId ? `(${activeRunId.slice(0, 8)})` : ''}</button>
        {activeReportId && <button className={tab === 'detail' ? 'tab active' : 'tab'} onClick={() => setTab('detail')}>报告详情</button>}
      </div>

      {tab === 'list' && (
        <>
          <div className="page-header">
            <input className="search-input" placeholder="搜索 run_id 或 agent" value={query} onChange={(event) => setQuery(event.target.value)} />
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
                      <td><input type="checkbox" checked={selectedReports.includes(r.run_id)} onChange={() => toggleCompare(r.run_id)} /></td>
                      <td><code>{r.run_id}</code></td>
                      <td>{r.agent_name}</td>
                      <td>{r.timestamp}</td>
                      <td>{r.overall_score?.toFixed(3) ?? '-'}</td>
                      <td className="actions-inline">
                        <button onClick={() => { setActiveReportId(r.run_id); setTab('detail') }}>详情</button>
                        <button className="danger" onClick={() => remove(r.run_id)}>删除</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {tab === 'monitor' && (
        activeRunId ? (
          <>
            <div className="page-header"><h2>运行监控</h2><span className={`status ${run?.status}`}>{run?.status || 'loading'}</span></div>
            <div className="cards">
              <ScoreCard title="总任务" value={progress?.total ?? 0} />
              <ScoreCard title="已完成" value={progress?.completed ?? 0} />
              <ScoreCard title="失败" value={progress?.failed ?? 0} />
              <ScoreCard title="整体分数" value={run?.summary?.overall_score} />
            </div>
            <div className="card">
              <div className="progress"><span style={{ width: `${percent}%` }} /></div>
              <p>{percent}% · 当前插件：{run?.current_plugin || '-'}</p>
              {run?.error && <p className="error">{run.error}</p>}
              {run?.report_id && <button onClick={() => { setActiveReportId(run.report_id!); setTab('detail') }}>查看报告</button>}
            </div>
            <div className="card"><h3>事件流</h3><EventLog events={events} /></div>
          </>
        ) : <div className="card"><p className="muted empty-hint">暂无运行任务，请先新建评测。</p></div>
      )}

      {tab === 'detail' && report && (
        <>
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
        </>
      )}

      <Modal open={showCompare} title={`报告对比（${selectedReports.length} 个）`} onClose={() => setShowCompare(false)} width="900px">
        {scoreData.length ? (
          <>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={scoreData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="run_id" hide /><YAxis domain={[0, 1]} /><Tooltip /><Legend /><Bar dataKey="score" fill="var(--accent)" /></BarChart>
            </ResponsiveContainer>
            <pre className="json-preview">{JSON.stringify(comparison?.comparison, null, 2)}</pre>
          </>
        ) : <p className="muted">请选择至少两个报告。</p>}
      </Modal>
    </section>
  )
}
