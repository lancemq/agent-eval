import { useEffect, useState } from 'react'
import { Layout } from './components/Layout'
import { Modal } from './components/Modal'
import { NewRunForm } from './components/NewRunForm'
import { DashboardPage } from './pages/DashboardPage'
import { ResourcesPage } from './pages/ResourcesPage'
import { RunsPage } from './pages/RunsPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [activeRunId, setActiveRunId] = useState<string>()
  const [activeReportId, setActiveReportId] = useState<string>()
  const [selectedReports, setSelectedReports] = useState<string[]>([])
  const [selectedTraceIds, setSelectedTraceIds] = useState<string[]>([])
  const [selectedScorers, setSelectedScorers] = useState<string[]>([])
  const [draftEvalConfig, setDraftEvalConfig] = useState<any>()
  const [showNewRunModal, setShowNewRunModal] = useState(false)
  const [runsInitialTab, setRunsInitialTab] = useState<'list' | 'monitor'>('list')

  useEffect(() => {
    if (draftEvalConfig) setShowNewRunModal(true)
  }, [draftEvalConfig])

  function openNewRun() { setShowNewRunModal(true) }

  function handleRunCreated(runId: string) {
    setActiveRunId(runId)
    setShowNewRunModal(false)
    setRunsInitialTab('monitor')
    setPage('runs')
  }

  function handleEvalCreated() {
    setPage('runs')
  }

  return (
    <Layout page={page} setPage={setPage}>
      {page === 'dashboard' && <DashboardPage setPage={setPage} onNewRun={openNewRun} />}
      {page === 'runs' && <RunsPage activeRunId={activeRunId} setActiveRunId={setActiveRunId} activeReportId={activeReportId} setActiveReportId={setActiveReportId} selectedReports={selectedReports} setSelectedReports={setSelectedReports} initialTab={runsInitialTab} />}
      {page === 'resources' && <ResourcesPage selectedTraceIds={selectedTraceIds} setSelectedTraceIds={setSelectedTraceIds} selectedScorers={selectedScorers} setSelectedScorers={setSelectedScorers} setDraftEvalConfig={setDraftEvalConfig} setPage={setPage} onEvalCreated={handleEvalCreated} />}
      {page === 'settings' && <SettingsPage setPage={setPage} />}

      <Modal open={showNewRunModal} title="新建评测" onClose={() => setShowNewRunModal(false)} width="1100px">
        <NewRunForm draftEvalConfig={draftEvalConfig} clearDraftEvalConfig={() => setDraftEvalConfig(undefined)} onCreated={handleRunCreated} />
      </Modal>
    </Layout>
  )
}
