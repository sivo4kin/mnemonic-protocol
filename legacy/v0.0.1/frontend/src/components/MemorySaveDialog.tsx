import { useState } from 'react'
import * as api from '../api'

interface Props {
  workspaceId: string
  initialContent: string
  sessionId?: string
  onClose: () => void
}

export default function MemorySaveDialog({ workspaceId, initialContent, sessionId, onClose }: Props) {
  const [memoryType, setMemoryType] = useState('finding')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!content.trim()) return
    setSaving(true)
    try {
      await api.saveMemory(workspaceId, {
        content,
        memory_type: memoryType,
        title: title || undefined,
        source_session_id: sessionId,
      })
      onClose()
    } catch (e) {
      alert(`Error saving: ${e}`)
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
        <h2 className="font-semibold text-lg mb-4">Save Memory</h2>

        <select value={memoryType} onChange={e => setMemoryType(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm mb-3">
          <option value="finding">Finding</option>
          <option value="decision">Decision</option>
          <option value="question">Open Question</option>
          <option value="source">Source / Reference</option>
        </select>

        <input placeholder="Title (optional)" value={title}
          onChange={e => setTitle(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm mb-3" />

        <textarea value={content} onChange={e => setContent(e.target.value)}
          rows={6} className="w-full border rounded-lg px-3 py-2 text-sm mb-4" />

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving || !content.trim()}
            className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50">
            {saving ? 'Saving...' : 'Save Memory'}
          </button>
        </div>
      </div>
    </div>
  )
}
