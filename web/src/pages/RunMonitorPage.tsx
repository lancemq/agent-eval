import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RunEvent, RunState } from '../api/types'
import { EventLog } from '../components/EventLog'
import { ScoreCard } from '../components/ScoreCard'

export function RunMonitorPage({ activeRunId, setPage, setActiveReportId }: { activeRunId?: string; setPage: (page: string) => void; setActiveReportId: (id: string) => void }) {
  const [run, setRun] = useState<RunState | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])

  useEffect(() => {
    if (!activeRunId) return
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

  if (!activeRunId) return <div className="card"><h2>暂无运行任务</h2><p>请先新建评测。</p></div>

  const progress = run?.progress
  const percent = progress && progress.total ? Math.round(((progress.completed + progress.failed) / progress.total) * 100) : 0

  return (
    <section>
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
        {run?.report_id && <button onClick={() => { setActiveReportId(run.report_id!); setPage('report-detail') }}>查看报告</button>}
      </div>
      <div className="card"><h3>事件流</h3><EventLog events={events} /></div>
    </section>
  )
}
