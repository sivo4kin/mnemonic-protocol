import { useEffect, useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { Workspace, Session, Message, MemoryItem, WorkspaceStats } from '../types'
import * as api from '../api'
import MemorySaveDialog from '../components/MemorySaveDialog'
import ProviderSwitch from '../components/ProviderSwitch'

export default function ActiveWorkspace() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSession, setActiveSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [lastMemoryContext, setLastMemoryContext] = useState<MemoryItem[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [showSaveMemory, setShowSaveMemory] = useState<string | null>(null)
  const [showProviderSwitch, setShowProviderSwitch] = useState(false)
  const [showNoteInput, setShowNoteInput] = useState(false)
  const [noteContent, setNoteContent] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const wsId = workspaceId!

  useEffect(() => {
    api.getWorkspace(wsId).then(setWorkspace)
    api.listSessions(wsId).then(s => { setSessions(s); if (s.length > 0) setActiveSession(s[0]) })
    api.getWorkspaceStats(wsId).then(setStats)
  }, [wsId])

  useEffect(() => {
    if (activeSession) {
      api.listMessages(wsId, activeSession.session_id).then(setMessages)
    }
  }, [wsId, activeSession])

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const startSession = async () => {
    const sess = await api.createSession(wsId, `Session ${sessions.length + 1}`)
    setSessions(prev => [sess, ...prev])
    setActiveSession(sess)
    setMessages([])
  }

  const handleSend = async () => {
    if (!input.trim() || sending || !activeSession) return
    setSending(true)
    const content = input
    setInput('')
    // Optimistic user message
    const tempMsg: Message = {
      message_id: 'temp', workspace_id: wsId, session_id: activeSession.session_id,
      role: 'user', content, provider_used: null, model_used: null, created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempMsg])
    try {
      const result = await api.sendMessage(wsId, activeSession.session_id, content)
      setMessages(prev => [
        ...prev.filter(m => m.message_id !== 'temp'),
        result.user_message, result.assistant_message,
      ])
      setLastMemoryContext(result.memory_context)
      api.getWorkspaceStats(wsId).then(setStats)
    } catch (e) {
      setMessages(prev => prev.filter(m => m.message_id !== 'temp'))
      setInput(content)
      alert(`Error: ${e}`)
    }
    setSending(false)
  }

  const handleSaveNote = async () => {
    if (!noteContent.trim()) return
    await api.addNote(wsId, noteContent)
    setNoteContent('')
    setShowNoteInput(false)
    api.getWorkspaceStats(wsId).then(setStats)
  }

  if (!workspace) return <div className="p-10 text-gray-400">Loading...</div>

  return (
    <div className="flex h-[calc(100vh-52px)]">
      {/* Left sidebar — sessions */}
      <div className="w-56 border-r bg-gray-50 flex flex-col">
        <div className="p-3 border-b">
          <button onClick={startSession}
            className="w-full bg-gray-900 text-white text-xs py-2 rounded-lg hover:bg-gray-800">
            New Session
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessions.map(s => (
            <button key={s.session_id} onClick={() => setActiveSession(s)}
              className={`w-full text-left px-3 py-2 text-sm border-b hover:bg-white ${
                activeSession?.session_id === s.session_id ? 'bg-white font-medium' : 'text-gray-600'
              }`}>
              {s.title || `Session`}
              <span className="block text-xs text-gray-400">{new Date(s.created_at).toLocaleDateString()}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Top bar */}
        <div className="border-b px-4 py-2 flex items-center justify-between bg-white">
          <h2 className="font-semibold text-sm">{workspace.name}</h2>
          <div className="flex items-center gap-3">
            <button onClick={() => setShowProviderSwitch(true)}
              className="text-xs bg-gray-100 px-2 py-1 rounded hover:bg-gray-200">
              {workspace.current_provider}/{workspace.current_model}
            </button>
            <Link to={`/workspace/${wsId}/memory`}
              className="text-xs text-blue-600 hover:underline">Memory Explorer</Link>
          </div>
        </div>

        {!activeSession ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <p className="mb-2">Start a session to begin your research.</p>
              <button onClick={startSession}
                className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm">New Session</button>
            </div>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && (
                <p className="text-center text-gray-400 text-sm mt-10">Send a message to start the conversation.</p>
              )}
              {messages.map(msg => (
                <div key={msg.message_id}
                  className={`max-w-2xl ${msg.role === 'user' ? 'ml-auto' : ''}`}>
                  <div className={`rounded-xl px-4 py-3 text-sm ${
                    msg.role === 'user'
                      ? 'bg-gray-900 text-white'
                      : 'bg-white border'
                  }`}>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                  {msg.role === 'assistant' && msg.message_id !== 'temp' && (
                    <button onClick={() => setShowSaveMemory(msg.content)}
                      className="text-xs text-gray-400 mt-1 hover:text-blue-600">
                      Save to memory
                    </button>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t p-3 bg-white">
              <div className="flex gap-2 max-w-3xl mx-auto">
                <input value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
                  placeholder="Ask something..." disabled={sending}
                  className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300" />
                <button onClick={handleSend} disabled={sending || !input.trim()}
                  className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50">
                  {sending ? '...' : 'Send'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Right sidebar — project state */}
      <div className="w-64 border-l bg-gray-50 overflow-y-auto text-xs">
        <div className="p-3 border-b">
          <h3 className="font-semibold text-sm mb-1">Project State</h3>
          {stats && (
            <div className="grid grid-cols-2 gap-1 text-gray-500">
              <span>{stats.memory_count} memories</span>
              <span>{stats.session_count} sessions</span>
              <span>{stats.message_count} messages</span>
              <span>{stats.source_count} sources</span>
            </div>
          )}
        </div>

        <div className="p-3 border-b">
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-semibold">Notes</h4>
            <button onClick={() => setShowNoteInput(!showNoteInput)} className="text-blue-600 hover:underline">+ Add</button>
          </div>
          {showNoteInput && (
            <div className="mb-2">
              <textarea value={noteContent} onChange={e => setNoteContent(e.target.value)}
                rows={3} placeholder="Paste a note..." className="w-full border rounded p-1 text-xs mb-1" />
              <button onClick={handleSaveNote} className="bg-gray-900 text-white px-2 py-1 rounded text-xs">Save Note</button>
            </div>
          )}
        </div>

        {stats && stats.recent_memories.length > 0 && (
          <div className="p-3 border-b">
            <h4 className="font-semibold mb-2">Recent Memories</h4>
            {stats.recent_memories.map(m => (
              <div key={m.memory_id} className="mb-2 p-2 bg-white rounded border">
                <span className="inline-block bg-gray-100 text-gray-600 px-1 rounded text-[10px] mb-1">{m.memory_type}</span>
                {m.title && <p className="font-medium">{m.title}</p>}
                <p className="text-gray-500 line-clamp-2">{m.content}</p>
              </div>
            ))}
          </div>
        )}

        {stats && stats.open_questions.length > 0 && (
          <div className="p-3">
            <h4 className="font-semibold mb-2">Open Questions</h4>
            {stats.open_questions.map(m => (
              <div key={m.memory_id} className="mb-2 p-2 bg-yellow-50 rounded border border-yellow-200">
                <p className="text-gray-700">{m.content}</p>
              </div>
            ))}
          </div>
        )}

        {lastMemoryContext.length > 0 && (
          <div className="p-3 border-t">
            <h4 className="font-semibold mb-2">Memory Used</h4>
            {lastMemoryContext.map(m => (
              <div key={m.memory_id} className="mb-2 p-2 bg-blue-50 rounded border border-blue-200">
                <span className="text-[10px] text-blue-600">{m.relevance_score?.toFixed(2)}</span>
                <p className="text-gray-700 line-clamp-2">{m.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dialogs */}
      {showSaveMemory && (
        <MemorySaveDialog
          workspaceId={wsId}
          initialContent={showSaveMemory}
          sessionId={activeSession?.session_id}
          onClose={() => { setShowSaveMemory(null); api.getWorkspaceStats(wsId).then(setStats) }}
        />
      )}
      {showProviderSwitch && (
        <ProviderSwitch
          workspaceId={wsId}
          onClose={() => { setShowProviderSwitch(false); api.getWorkspace(wsId).then(setWorkspace) }}
        />
      )}
    </div>
  )
}
