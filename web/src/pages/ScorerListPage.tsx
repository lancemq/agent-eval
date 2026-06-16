import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ScorerInfo } from '../api/types'

type Props = {
  selectedScorers: string[]
  setSelectedScorers: (ids: string[]) => void
  setPage: (page: string) => void
}

export function ScorerListPage({ selectedScorers, setSelectedScorers, setPage }: Props) {
  const [scorers, setScorers] = useState<ScorerInfo[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    api.scorers().then(setScorers).catch(console.error)
  }, [])

  const filtered = useMemo(() => scorers.filter((scorer) => `${scorer.type} ${scorer.description}`.toLowerCase().includes(query.toLowerCase())), [scorers, query])

  function toggle(type: string) {
    setSelectedScorers(selectedScorers.includes(type) ? selectedScorers.filter((item) => item !== type) : [...selectedScorers, type])
  }

  return (
    <section>
      <div className="page-header">
        <h2>Scorer 列表</h2>
        <div className="actions-inline">
          <button onClick={() => setSelectedScorers([])}>清空选择</button>
          <button className="primary" onClick={() => setPage('traces')}>用于 Trace Eval</button>
        </div>
      </div>
      <div className="cards">
        <div className="card score-card"><span>Scorer 总数</span><strong>{scorers.length}</strong></div>
        <div className="card score-card"><span>已选择</span><strong>{selectedScorers.length}</strong></div>
        <div className="card score-card"><span>精确匹配</span><strong>{scorers.some((item) => item.type === 'exact_match') ? '可用' : '-'}</strong></div>
        <div className="card score-card"><span>Agent 评分</span><strong>{scorers.filter((item) => item.type.includes('task') || item.type.includes('tool')).length}</strong></div>
      </div>
      <div className="card">
        <input placeholder="搜索 scorer 类型或描述" value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="plugin-grid list-grid">
          {filtered.map((scorer) => (
            <label key={scorer.type} className="card plugin-card">
              <input type="checkbox" checked={selectedScorers.includes(scorer.type)} onChange={() => toggle(scorer.type)} />
              <div>
                <strong>{scorer.type}</strong>
                <p>{scorer.description}</p>
              </div>
            </label>
          ))}
        </div>
      </div>
    </section>
  )
}
