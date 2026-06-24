import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

type Props = {
  children: ReactNode
}

const mainNav: Array<[string, string]> = [
  ['/', '总览'],
  ['/run', '新建评测'],
  ['/live', '运行监测'],
  ['/library', '资源库'],
  ['/reports', '报告'],
]

const bottomNav: Array<[string, string]> = [
  ['/settings', '设置'],
]

export function Layout({ children }: Props) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>AgentEval</h1>
        <p>本地评测控制台</p>
        <nav>
          {mainNav.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {bottomNav.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}
