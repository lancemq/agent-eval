import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export function DimensionChart({ dimensions }: { dimensions?: Record<string, number> }) {
  const data = Object.entries(dimensions || {}).map(([name, score]) => ({ name, score }))
  if (!data.length) return <p className="muted">暂无维度分数</p>
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis domain={[0, 1]} />
          <Tooltip />
          <Bar dataKey="score" fill="#4f46e5" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
