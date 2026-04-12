import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Workspace } from '../types'
import * as api from '../api'

export default function WorkspaceHome() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('gpt-4o')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  useEffect(() => { api.listWorkspaces().then(setWorkspaces).catch(console.error) }, [])

  const handleCreate = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      const ws = await api.createWorkspace({ name, description, provider, model })
      navigate(`/workspace/${ws.workspace_id}`)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Workspaces</h1>
        <button onClick={() => setShowCreate(true)}
          className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800">
          New Workspace
        </button>
      </div>

      {showCreate && (
        <div className="bg-white border rounded-xl p-6 mb-8 shadow-sm">
          <h2 className="font-semibold mb-4">Create Workspace</h2>
          <input placeholder="Project name" value={name} onChange={e => setName(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 mb-3 text-sm" />
          <textarea placeholder="Description (optional)" value={description}
            onChange={e => setDescription(e.target.value)} rows={2}
            className="w-full border rounded-lg px-3 py-2 mb-3 text-sm" />
          <div className="flex gap-3 mb-4">
            <select value={provider} onChange={e => setProvider(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm flex-1">
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="qwen">Qwen</option>
            </select>
            <select value={model} onChange={e => setModel(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm flex-1">
              {provider === 'anthropic' && <>
                <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
              </>}
              {provider === 'openai' && <>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4o-mini">GPT-4o Mini</option>
              </>}
              {provider === 'qwen' && <>
                <option value="qwen-plus">Qwen Plus</option>
                <option value="qwen-turbo">Qwen Turbo</option>
              </>}
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={loading || !name.trim()}
              className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50">
              {loading ? 'Creating...' : 'Create'}
            </button>
            <button onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100">
              Cancel
            </button>
          </div>
        </div>
      )}

      {workspaces.length === 0 && !showCreate && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg mb-2">No workspaces yet</p>
          <p className="text-sm">Create your first research workspace to get started.</p>
        </div>
      )}

      <div className="grid gap-4">
        {workspaces.map(ws => (
          <button key={ws.workspace_id} onClick={() => navigate(`/workspace/${ws.workspace_id}`)}
            className="bg-white border rounded-xl p-5 text-left hover:border-gray-400 transition shadow-sm">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="font-semibold text-lg">{ws.name}</h3>
                {ws.description && <p className="text-sm text-gray-500 mt-1">{ws.description}</p>}
              </div>
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                {ws.current_provider}/{ws.current_model}
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Updated {new Date(ws.updated_at).toLocaleDateString()}
            </p>
          </button>
        ))}
      </div>
    </div>
  )
}
