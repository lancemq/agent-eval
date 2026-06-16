import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { PluginInfo } from '../api/types'

type Props = {
  setPage: (page: string) => void
}

export function PluginListPage({ setPage }: Props) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    api.plugins().then(setPlugins).catch(console.error)
  }, [])

  const filtered = useMemo(() => plugins.filter((plugin) => `${plugin.name} ${plugin.type} ${plugin.description} ${plugin.dimensions.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [plugins, query])
  const byType = plugins.reduce<Record<string, number>>((acc, plugin) => {
    acc[plugin.type] = (acc[plugin.type] || 0) + 1
    return acc
  }, {})

  return (
    <section>
      <div className="page-header">
        <h2>插件列表</h2>
        <button className="primary" onClick={() => setPage('run')}>新建评测</button>
      </div>
      <div className="cards">
        <div className="card score-card"><span>插件总数</span><strong>{plugins.length}</strong></div>
        <div className="card score-card"><span>Benchmark</span><strong>{byType.benchmark || 0}</strong></div>
        <div className="card score-card"><span>Dynamic</span><strong>{byType.dynamic || 0}</strong></div>
        <div className="card score-card"><span>Custom</span><strong>{byType.custom || 0}</strong></div>
      </div>
      <div className="card">
        <input placeholder="搜索插件、类型或维度" value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="plugin-grid list-grid">
          {filtered.map((plugin) => (
            <div key={plugin.name} className="card plugin-card standalone-card">
              <div>
                <strong>{plugin.name}</strong>
                <small>{plugin.type} · v{plugin.version}</small>
                <p>{plugin.description || '无描述'}</p>
                <div className="tags">{plugin.dimensions.map((dim) => <span key={dim}>{dim}</span>)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
