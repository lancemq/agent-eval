import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { EventLog } from '../components/EventLog'
import { ScoreCard } from '../components/ScoreCard'
import type { ReportListItem, RunEvent, RunState } from '../api/types'

export function LivePage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [recentRuns, setRecentRuns] = useState<ReportListItem[]>([])
  const [run, setRun] = useState<RunState | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])

  useEffect(() => {
    api.reports().then(setRecentRuns).catch(console.error)
  }, [])

  // Monitor a specific run
  useEffect(() => {
    if (!runId) {
      setRun(null)
      setEvents([])
      return
    }
    setEvents([])
    let stopped = false

    const source = new EventSource(`/api/runs/${runId}/events`)
    source.onmessage = (message) => setEvents((items) => [...items, JSON.parse(message.data)])
    const knownEvents = ['run_queued', 'evaluation_start', 'evaluator_setup', 'task_generated', 'task_execute', 'task_evaluate', 'task_complete', 'task_failed', 'evaluator_teardown', 'evaluation_complete', 'evaluation_failed']
    knownEvents.forEach((name) => source.addEventListener(name, (message) => setEvents((items) => [...items, JSON.parse((message as MessageEvent).data)])))

    const interval = window.setInterval(async () => {
      if (!stopped) setRun(await api.run(runId))
    }, 1000)
    api.run(runId).then(setRun).catch(console.error)

    return () => {
      stopped = true
      source.close()
      window.clearInterval(interval)
    }
  }, [runId])

  const progress = run?.progress
  const percent = progress && progress.total ? Math.round(((progress.completed + progress.failed) / progress.total) * 100) : 0

  return (
    <section>
      <div className="page-header">
        <h2>实验监测</h2>
        {runId && <span className={`status ${run?.status}`}>{run?.status || 'loading'}</span>}
      </div>

      {runId ? (
        <>
          <div className="cards">
            <ScoreCard title="总任务" value={progress?.total ?? 0} />
            <ScoreCard title="已完成" value={progress?.completed ?? 0} />
            <ScoreCard title="失败" value={progress?.failed ?? 0} />
            <ScoreCard title="整体分数" value={run?.summary?.overall_score} />
          </div>
          <div className="card">
            <div className="progress"><span style={{ width: `${percent}%` }} /></div>
            <p>{percent}% · 当前评估器：{run?.current_evaluator || '-'}</p>
            {run?.error && <p className="error">{run.error}</p>}
            {run?.report_id && (
              <div className="actions-inline" style={{ marginTop: 8 }}>
                <button onClick={() => navigate(`/reports/${run.report_id!}`)}>查看报告</button>
                <button onClick={() => navigate('/live')}>返回列表</button>
              </div>
            )}
          </div>
          <div className="card"><h3>事件流</h3><EventLog events={events} /></div>
        </>
      ) : (
        <div className="card">
          <h3>最近实验记录</h3>
          {recentRuns.length === 0 ? (
            <p className="muted empty-hint">暂无实验记录，请先新建实验。</p>
          ) : (
            <table>
              <thead><tr><th>实验 ID</th><th>Agent</th><th>时间</th><th>分数</th><th>操作</th></tr></thead>
              <tbody>
                {recentRuns.map((r) => (
                  <tr key={r.run_id}>
                    <td><code>{r.run_id}</code></td>
                    <td>{r.agent_name}</td>
                    <td>{r.timestamp}</td>
                    <td>{r.overall_score?.toFixed(3) ?? '-'}</td>
                    <td>
                      <button onClick={() => navigate(`/live/${r.run_id}`)}>监控</button>
                      <button onClick={() => navigate(`/reports/${r.run_id}`)}>报告</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  )
}