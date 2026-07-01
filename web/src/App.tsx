import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { RunPage } from './pages/RunPage'
import { LivePage } from './pages/LivePage'
import { LibraryPage } from './pages/LibraryPage'
import { ReportsPage } from './pages/ReportsPage'
import { SettingsPage } from './pages/SettingsPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { CreateDatasetPage } from './pages/CreateDatasetPage'
import { PromptsPage, CreatePromptPage } from './pages/PromptsPage'
import { ReviewsPage } from './pages/ReviewsPage'
import { PlaygroundPage } from './pages/PlaygroundPage'
import { TrendPage } from './pages/TrendPage'

export default function App() {
  return (
    <HashRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/run" element={<RunPage />} />
          <Route path="/live" element={<LivePage />} />
          <Route path="/live/:runId" element={<LivePage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/datasets/new" element={<CreateDatasetPage />} />
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/prompts/new" element={<CreatePromptPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/reviews/:name" element={<ReviewsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/reports/:reportId" element={<ReportsPage />} />
          <Route path="/trend" element={<TrendPage />} />
          <Route path="/playground" element={<PlaygroundPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/:tab" element={<LibraryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </HashRouter>
  )
}
