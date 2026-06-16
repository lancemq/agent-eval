type Props = {
  title: string
  value?: number | string
  suffix?: string
}

export function ScoreCard({ title, value, suffix }: Props) {
  const shown = typeof value === 'number' ? value.toFixed(3) : value ?? '-'
  return (
    <div className="card score-card">
      <span>{title}</span>
      <strong>{shown}{suffix || ''}</strong>
    </div>
  )
}
