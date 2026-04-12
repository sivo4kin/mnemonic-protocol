export interface Workspace {
  workspace_id: string
  name: string
  description: string
  status: string
  current_provider: string
  current_model: string
  created_at: string
  updated_at: string
}

export interface Session {
  session_id: string
  workspace_id: string
  title: string | null
  status: string
  started_at: string
  ended_at: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  message_id: string
  workspace_id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  provider_used: string | null
  model_used: string | null
  created_at: string
}

export interface MemoryItem {
  memory_id: string
  workspace_id: string
  source_session_id: string | null
  source_message_id: string | null
  memory_type: string
  title: string | null
  content: string
  tags: string[]
  is_pinned: boolean
  created_at: string
  updated_at: string
  relevance_score?: number
}

export interface SourceContext {
  source_id: string
  workspace_id: string
  source_type: string
  display_name: string | null
  content: string
  created_at: string
}

export interface ApiResponse<T> {
  ok: boolean
  data: T
  error?: { code: string; message: string }
}

export interface AskResult {
  user_message: Message
  assistant_message: Message
  memory_context: MemoryItem[]
}

export interface ProviderBinding {
  provider: string
  model: string
  status: string
  available_providers: { provider: string; models: string[] }[]
}

export interface WorkspaceStats {
  memory_count: number
  session_count: number
  message_count: number
  source_count: number
  recent_memories: MemoryItem[]
  open_questions: MemoryItem[]
}
