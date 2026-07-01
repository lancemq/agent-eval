import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { TrendResponse } from '../api/types'

export function TrendPage() {
  const [data, setData] = useState<TrendResponse | null>(null)
  const [agentName, setAgentName] = useState<string>('')
  const [message, setMessage] = useState('')

  async function load(agent?: string) {
    try {
      const d = await api.trend(agent || undefined, 100)
      setData(d)
      if (!agent && d.agents.length > 0) setAgentName(d.agents[0])
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '加载失败')
    }
  }

  useEffect(() => { load() }, [])

  const chartData = useMemo(() => {
    if (!data) return []
    return data.points.map((p) => ({
      run_id: p.run_id.slice(0, 8),
      timestamp: p.timestamp.slice(0, 10),
      overall: p.overall_score ?? null,
      pass_rate: p.pass_rate ?? null,
      ...p.dimensions,
    }))
  }, [data])

  const dimensionKeys = useMemo(() => {
    if (!data) return []
    return Object.keys(data.dimension_trends)
  }, [data])

  const dimensionChart = useMemo(() => {
    if (!data) return []
    const points = data.points
    return dimensionKeys.map((dim) => ({
      dim,
      series: points.map((p) => ({
        run_id: p.run_id.slice(0, 8),
        timestamp: p.timestamp.slice(0, 10),
        score: p.dimensions[dim] ?? null,
      })),
      ci: data.dimension_ci?.[dim],
    }))
  }, [data, dimensionKeys])

  if (!data) {
    return <section><div className="card"><p className="muted">加载中...</p>{message && <p className="message">{message}</p>}</div></section>
  }

  const trendArrow = data.overall_ci?.trend === 'up' ? '↑' : data.overall_ci?.trend === 'down' ? '↓' : '→'
  const trendColor = data.overall_ci?.trend === 'up' ? 'var(--success, #27ae60)' : data.overall_ci?.trend === 'down' ? 'var(--danger, #c0392b)' : 'var(--muted, #888)'

  return (
    <section>
      <div className="page-header">
        <h2>趋势分析</h2>
        <div className="actions-inline">
          <select value={agentName} onChange={(e) => { setAgentName(e.target.value); load(e.target.value) }} className="search-input">
            {data.agents.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <span className="muted">{data.points.length} 次运行</span>
        </div>
      </div>
      {message && <p className="message">{message}</p>}

      {/* 统计摘要卡片 */}
      {data.overall_ci && data.overall_ci.mean != null && (
        <div className="cards">
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="muted" style={{ fontSize: 12 }}>Overall 均值</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{data.overall_ci.mean?.toFixed(3) ?? '-'}</div>
            <div className="muted" style={{ fontSize: 11 }}>95% CI: [{data.overall_ci.ci_low?.toFixed(3) ?? '-'}, {data.overall_ci.ci_high?.toFixed(3) ?? '-'}]</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="muted" style={{ fontSize: 12 }}>趋势方向</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: trendColor }}>{trendArrow}</div>
            <div className="muted" style={{ fontSize: 11 }}>{data.overall_ci.trend ?? '-'}</div>
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="muted" style={{ fontSize: 12 }}>通过率均值</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{data.pass_rate_ci?.mean != null ? (data.pass_rate_ci.mean * 100).toFixed(1) : '-'}%</div>
            {data.pass_rate_ci?.mean != null && <div className="muted" style={{ fontSize: 11 }}>95% CI: [{(data.pass_rate_ci.ci_low * 100).toFixed(1)}%, {(data.pass_rate_ci.ci_high * 100).toFixed(1)}%]</div>}
          </div>
          <div className="card" style={{ textAlign: 'center' }}>
            <div className="muted" style={{ fontSize: 12 }}>样本数</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{data.overall_ci.n}</div>
            <div className="muted" style={{ fontSize: 11 }}>次实验</div>
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="section-title">总体分数与通过率趋势</h3>
        {chartData.length === 0 ? (
          <p className="muted empty-hint">该 Agent 暂无历史实验记录</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="timestamp" fontSize={11} />
              <YAxis domain={[0, 1]} fontSize={11} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="overall" name="overall_score" stroke="#3b82f6" dot={{ r: 3 }} />
              <Line type="monotone" dataKey="pass_rate" name="pass_rate" stroke="#10b981" dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {dimensionChart.map((d) => (
        <div key={d.dim} className="card">
          <h3 className="section-title">
            指标：{d.dim}
            {d.ci && <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>均值 {d.ci.mean.toFixed(3)} · 95% CI [{d.ci.ci_low.toFixed(3)}, {d.ci.ci_high.toFixed(3)}] · n={d.ci.n}</span>}
          </h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={d.series} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="timestamp" fontSize={11} />
              <YAxis domain={[0, 1]} fontSize={11} />
              <Tooltip />
              <Line type="monotone" dataKey="score" name={d.dim} stroke="#f59e0b" dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ))}
    </section>
  )
}
