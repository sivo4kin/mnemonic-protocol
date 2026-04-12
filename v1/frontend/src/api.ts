import type { ApiResponse, Workspace, Session, Message, MemoryItem, AskResult, ProviderBinding, SourceContext, WorkspaceStats } from './types'

const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const json: ApiResponse<T> = await res.json()
  if (!json.ok) throw new Error(json.error?.message || 'Unknown error')
  return json.data
}

// Workspaces
export const listWorkspaces = () => request<Workspace[]>('/workspaces')
export const createWorkspace = (body: { name: string; description?: string; provider?: string; model?: string }) =>
  request<Workspace>('/workspaces', { method: 'POST', body: JSON.stringify(body) })
export const getWorkspace = (id: string) => request<Workspace>(`/workspaces/${id}`)
export const updateWorkspace = (id: string, body: Record<string, unknown>) =>
  request<Workspace>(`/workspaces/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

// Sessions
export const listSessions = (wsId: string) => request<Session[]>(`/workspaces/${wsId}/sessions`)
export const createSession = (wsId: string, title?: string) =>
  request<Session>(`/workspaces/${wsId}/sessions`, { method: 'POST', body: JSON.stringify({ title }) })

// Messages
export const listMessages = (wsId: string, sessId: string) =>
  request<Message[]>(`/workspaces/${wsId}/sessions/${sessId}/messages`)
export const sendMessage = (wsId: string, sessId: string, content: string, topK = 10) =>
  request<AskResult>(`/workspaces/${wsId}/sessions/${sessId}/messages`, {
    method: 'POST', body: JSON.stringify({ content, top_k_memories: topK }),
  })

// Memories
export const listMemories = (wsId: string, params?: Record<string, string>) => {
  const qs = params ? '?' + new URLSearchParams(params).toString() : ''
  return request<MemoryItem[]>(`/workspaces/${wsId}/memories${qs}`)
}
export const searchMemories = (wsId: string, query: string, k = 20) =>
  request<MemoryItem[]>(`/workspaces/${wsId}/memories?q=${encodeURIComponent(query)}&k=${k}`)
export const saveMemory = (wsId: string, body: { content: string; memory_type?: string; title?: string; tags?: string[]; source_session_id?: string; source_message_id?: string }) =>
  request<MemoryItem>(`/workspaces/${wsId}/memories`, { method: 'POST', body: JSON.stringify(body) })
export const getMemory = (wsId: string, memId: string) =>
  request<MemoryItem>(`/workspaces/${wsId}/memories/${memId}`)
export const updateMemory = (wsId: string, memId: string, body: Record<string, unknown>) =>
  request<MemoryItem>(`/workspaces/${wsId}/memories/${memId}`, { method: 'PATCH', body: JSON.stringify(body) })

// Provider
export const getProviderBinding = (wsId: string) =>
  request<ProviderBinding>(`/workspaces/${wsId}/provider-binding`)
export const switchProvider = (wsId: string, provider: string, model: string) =>
  request<Record<string, unknown>>(`/workspaces/${wsId}/provider-binding/switch`, {
    method: 'POST', body: JSON.stringify({ provider, model }),
  })

// Sources
export const listSources = (wsId: string) => request<SourceContext[]>(`/workspaces/${wsId}/sources`)
export const addNote = (wsId: string, content: string, displayName?: string) =>
  request<SourceContext>(`/workspaces/${wsId}/sources/note`, {
    method: 'POST', body: JSON.stringify({ content, display_name: displayName }),
  })

// Stats
export const getWorkspaceStats = (wsId: string) => request<WorkspaceStats>(`/workspaces/${wsId}/stats`)
