import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { MemoryItem } from '../types'
import * as api from '../api'

const TYPES = ['', 'finding', 'decision', 'question', 'source']

export default function MemoryExplorer() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [selected, setSelected] = useState<MemoryItem | null>(null)

  const wsId = workspaceId!

  useEffect(() => { loadMemories() }, [wsId, typeFilter])

  const loadMemories = async () => {
    const params: Record<string, string> = {}
    if (typeFilter) params.type = typeFilter
    const data = await api.listMemories(wsId, params)
    setMemories(data)
  }

  const handleSearch = async () => {
    if (!query.trim()) { loadMemories(); return }
    const data = await api.searchMemories(wsId, query)
    setMemories(data)
  }

  return (
    <div className="flex h-[calc(100vh-52px)]">
      {/* List */}
      <div className="flex-1 flex flex-col">
        <div className="border-b px-4 py-3 bg-white flex items-center gap-3">
          <Link to={`/workspace/${wsId}`} className="text-sm text-gray-500 hover:text-gray-900">&larr; Workspace</Link>
          <h2 className="font-semibold text-sm">Memory Explorer</h2>
        </div>

        <div className="px-4 py-3 border-b bg-white flex gap-2">
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="Search memories..." className="flex-1 border rounded-lg px-3 py-2 text-sm" />
          <button onClick={handleSearch} className="bg-gray-900 text-white px-3 py-2 rounded-lg text-sm">Search</button>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
            className="border rounded-lg px-2 py-2 text-sm">
            <option value="">All types</option>
            {TYPES.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {memories.length === 0 && (
            <p className="text-center text-gray-400 text-sm mt-10">No memories found.</p>
          )}
          {memories.map(m => (
            <button key={m.memory_id} onClick={() => setSelected(m)}
              className={`w-full text-left p-4 rounded-xl border hover:border-gray-400 transition ${
                selected?.memory_id === m.memory_id ? 'border-gray-900 bg-white shadow-sm' : 'bg-white'
              }`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  m.memory_type === 'finding' ? 'bg-green-100 text-green-700' :
                  m.memory_type === 'decision' ? 'bg-blue-100 text-blue-700' :
                  m.memory_type === 'question' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-600'
                }`}>{m.memory_type}</span>
                {m.is_pinned && <span className="text-[10px] text-amber-500">pinned</span>}
                {'relevance_score' in m && m.relevance_score !== undefined && (
                  <span className="text-[10px] text-gray-400 ml-auto">{m.relevance_score.toFixed(3)}</span>
                )}
              </div>
              {m.title && <p className="font-medium text-sm">{m.title}</p>}
              <p className="text-sm text-gray-600 line-clamp-2">{m.content}</p>
              <p className="text-[10px] text-gray-400 mt-1">{new Date(m.created_at).toLocaleString()}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="w-96 border-l bg-gray-50 overflow-y-auto">
        {selected ? (
          <div className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                selected.memory_type === 'finding' ? 'bg-green-100 text-green-700' :
                selected.memory_type === 'decision' ? 'bg-blue-100 text-blue-700' :
                selected.memory_type === 'question' ? 'bg-yellow-100 text-yellow-700' :
                'bg-gray-100 text-gray-600'
              }`}>{selected.memory_type}</span>
              {selected.is_pinned && <span className="text-xs text-amber-500">pinned</span>}
            </div>
            {selected.title && <h3 className="font-semibold text-lg mb-2">{selected.title}</h3>}
            <div className="bg-white rounded-lg border p-4 text-sm whitespace-pre-wrap mb-4">
              {selected.content}
            </div>
            {selected.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-4">
                {selected.tags.map(t => (
                  <span key={t} className="text-[10px] bg-gray-200 px-1.5 py-0.5 rounded">{t}</span>
                ))}
              </div>
            )}
            <div className="text-xs text-gray-400 space-y-1">
              <p>Created: {new Date(selected.created_at).toLocaleString()}</p>
              <p>Updated: {new Date(selected.updated_at).toLocaleString()}</p>
              {selected.source_session_id && <p>Source session: {selected.source_session_id.slice(0, 8)}...</p>}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Select a memory to view details
          </div>
        )}
      </div>
    </div>
  )
}
