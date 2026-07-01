import type { EvaluatorInfo } from '../api/types'

type Props = {
  evaluators: EvaluatorInfo[]
  selected: string[]
  onChange: (selected: string[]) => void
}

export function EvaluatorSelector({ evaluators, selected, onChange }: Props) {
  function toggle(name: string) {
    onChange(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name])
  }

  return (
    <div className="evaluator-grid">
      {evaluators.map((evaluator) => (
        <label key={evaluator.name} className="card evaluator-card">
          <input type="checkbox" checked={selected.includes(evaluator.name)} onChange={() => toggle(evaluator.name)} />
          <div>
            <strong>{evaluator.name}</strong>
            <small>{evaluator.type} · v{evaluator.version}</small>
            <p>{evaluator.description || '无描述'}</p>
            <div className="tags">{evaluator.dimensions.map((dim) => <span key={dim}>{dim}</span>)}</div>
          </div>
        </label>
      ))}
    </div>
  )
}
