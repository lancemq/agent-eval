import { useEffect, useState } from 'react'
import { Layout } from './components/Layout'
import { Modal } from './components/Modal'
import { NewRunForm } from './components/NewRunForm'
import { LangfuseEvalWizard } from './components/LangfuseEvalWizard'
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
  const [showWizard, setShowWizard] = useState(false)
  const [runsInitialTab, setRunsInitialTab] = useState<'list' | 'monitor'>('list')

  useEffect(() => {
    if (draftEvalConfig) setShowNewRunModal(true)
  }, [draftEvalConfig])

  function openNewRun() { setShowNewRunModal(true) }
  function openWizard() { setShowWizard(true) }

  function handleRunCreated(runId: string) {
    setActiveRunId(runId)
    setShowNewRunModal(false)
    setShowWizard(false)
    setRunsInitialTab('monitor')
    setPage('runs')
  }

  function handleEvalCreated() {
    setPage('runs')
  }

  return (
    <Layout page={page} setPage={setPage}>
      {page === 'dashboard' && <DashboardPage setPage={setPage} onNewRun={openNewRun} onOpenWizard={openWizard} />}
      {page === 'runs' && <RunsPage activeRunId={activeRunId} setActiveRunId={setActiveRunId} activeReportId={activeReportId} setActiveReportId={setActiveReportId} selectedReports={selectedReports} setSelectedReports={setSelectedReports} initialTab={runsInitialTab} />}
      {page === 'resources' && <ResourcesPage selectedTraceIds={selectedTraceIds} setSelectedTraceIds={setSelectedTraceIds} selectedScorers={selectedScorers} setSelectedScorers={setSelectedScorers} setDraftEvalConfig={setDraftEvalConfig} setPage={setPage} onEvalCreated={handleEvalCreated} />}
      {page === 'settings' && <SettingsPage setPage={setPage} />}

      <Modal open={showNewRunModal} title="新建评测" onClose={() => setShowNewRunModal(false)} width="1100px">
        <NewRunForm draftEvalConfig={draftEvalConfig} clearDraftEvalConfig={() => setDraftEvalConfig(undefined)} onCreated={handleRunCreated} />
      </Modal>

      <Modal open={showWizard} title="从 Langfuse Trace 生成评测" onClose={() => setShowWizard(false)} width="900px">
        <LangfuseEvalWizard onClose={() => setShowWizard(false)} onCreated={handleRunCreated} />
      </Modal>
    </Layout>
  )
}
