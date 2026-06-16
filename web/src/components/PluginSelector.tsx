import type { PluginInfo } from '../api/types'

type Props = {
  plugins: PluginInfo[]
  selected: string[]
  onChange: (selected: string[]) => void
}

export function PluginSelector({ plugins, selected, onChange }: Props) {
  function toggle(name: string) {
    onChange(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name])
  }

  return (
    <div className="plugin-grid">
      {plugins.map((plugin) => (
        <label key={plugin.name} className="card plugin-card">
          <input type="checkbox" checked={selected.includes(plugin.name)} onChange={() => toggle(plugin.name)} />
          <div>
            <strong>{plugin.name}</strong>
            <small>{plugin.type} · v{plugin.version}</small>
            <p>{plugin.description || '无描述'}</p>
            <div className="tags">{plugin.dimensions.map((dim) => <span key={dim}>{dim}</span>)}</div>
          </div>
        </label>
      ))}
    </div>
  )
}
