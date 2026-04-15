import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import WorkspaceHome from './pages/WorkspaceHome'
import ActiveWorkspace from './pages/ActiveWorkspace'
import MemoryExplorer from './pages/MemoryExplorer'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<WorkspaceHome />} />
        <Route path="/workspace/:workspaceId" element={<ActiveWorkspace />} />
        <Route path="/workspace/:workspaceId/memory" element={<MemoryExplorer />} />
      </Routes>
    </Layout>
  )
}
