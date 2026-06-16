import { useState } from 'react'
import { Layout } from './components/Layout'
import { ComparePage } from './pages/ComparePage'
import { DashboardPage } from './pages/DashboardPage'
import { PluginListPage } from './pages/PluginListPage'
import { ReportDetailPage } from './pages/ReportDetailPage'
import { ReportsPage } from './pages/ReportsPage'
import { RunMonitorPage } from './pages/RunMonitorPage'
import { RunSetupPage } from './pages/RunSetupPage'
import { ScorerListPage } from './pages/ScorerListPage'
import { SettingsPage } from './pages/SettingsPage'
import { TraceListPage } from './pages/TraceListPage'

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [activeRunId, setActiveRunId] = useState<string>()
  const [activeReportId, setActiveReportId] = useState<string>()
  const [selectedReports, setSelectedReports] = useState<string[]>([])
  const [selectedTraceIds, setSelectedTraceIds] = useState<string[]>([])
  const [selectedScorers, setSelectedScorers] = useState<string[]>([])
  const [draftEvalConfig, setDraftEvalConfig] = useState<any>()

  return (
    <Layout page={page} setPage={setPage}>
      {page === 'dashboard' && <DashboardPage setPage={setPage} />}
      {page === 'run' && <RunSetupPage setPage={setPage} setActiveRunId={setActiveRunId} draftEvalConfig={draftEvalConfig} clearDraftEvalConfig={() => setDraftEvalConfig(undefined)} />}
      {page === 'traces' && <TraceListPage selectedTraceIds={selectedTraceIds} setSelectedTraceIds={setSelectedTraceIds} selectedScorers={selectedScorers} setSelectedScorers={setSelectedScorers} setDraftEvalConfig={setDraftEvalConfig} setPage={setPage} />}
      {page === 'scorers' && <ScorerListPage selectedScorers={selectedScorers} setSelectedScorers={setSelectedScorers} setPage={setPage} />}
      {page === 'plugins' && <PluginListPage setPage={setPage} />}
      {page === 'settings' && <SettingsPage setPage={setPage} />}
      {page === 'monitor' && <RunMonitorPage activeRunId={activeRunId} setPage={setPage} setActiveReportId={setActiveReportId} />}
      {page === 'reports' && <ReportsPage setPage={setPage} setActiveReportId={setActiveReportId} selectedReports={selectedReports} setSelectedReports={setSelectedReports} />}
      {page === 'report-detail' && <ReportDetailPage activeReportId={activeReportId} />}
      {page === 'compare' && <ComparePage selectedReports={selectedReports} setSelectedReports={setSelectedReports} />}
    </Layout>
  )
}
