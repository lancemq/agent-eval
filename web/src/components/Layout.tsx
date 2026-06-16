import type { ReactNode } from 'react'

type Props = {
  page: string
  setPage: (page: string) => void
  children: ReactNode
}

const nav = [
  ['dashboard', '总览'],
  ['runs', '评测'],
  ['resources', '资源'],
  ['settings', '设置'],
]

export function Layout({ page, setPage, children }: Props) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>AgentEval</h1>
        <p>本地评测控制台</p>
        <nav>
          {nav.map(([key, label]) => (
            <button key={key} className={page === key ? 'active' : ''} onClick={() => setPage(key)}>
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}
