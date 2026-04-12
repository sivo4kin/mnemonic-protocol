import { useEffect, useState } from 'react'
import type { ProviderBinding } from '../types'
import * as api from '../api'

interface Props {
  workspaceId: string
  onClose: () => void
}

const MODEL_OPTIONS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-20250514', 'claude-haiku-4-5-20251001'],
  openai: ['gpt-4o', 'gpt-4o-mini'],
  qwen: ['qwen-plus', 'qwen-turbo'],
}

export default function ProviderSwitch({ workspaceId, onClose }: Props) {
  const [binding, setBinding] = useState<ProviderBinding | null>(null)
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [switching, setSwitching] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.getProviderBinding(workspaceId).then(b => {
      setBinding(b)
      setProvider(b.provider)
      setModel(b.model)
    })
  }, [workspaceId])

  const handleSwitch = async () => {
    if (!provider || !model) return
    setSwitching(true)
    setMessage('')
    try {
      await api.switchProvider(workspaceId, provider, model)
      setMessage('Provider switched. Workspace memory preserved.')
      setTimeout(onClose, 1000)
    } catch (e) {
      setMessage(`Switch failed: ${e}`)
    }
    setSwitching(false)
  }

  const models = MODEL_OPTIONS[provider] || []

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 className="font-semibold text-lg mb-1">Switch Provider</h2>
        <p className="text-xs text-gray-500 mb-4">Memory is preserved across provider switches.</p>

        {binding && (
          <p className="text-sm mb-4 bg-gray-50 rounded-lg p-3">
            Current: <strong>{binding.provider}/{binding.model}</strong>
          </p>
        )}

        <select value={provider} onChange={e => { setProvider(e.target.value); setModel(MODEL_OPTIONS[e.target.value]?.[0] || '') }}
          className="w-full border rounded-lg px-3 py-2 text-sm mb-3">
          <option value="">Select provider</option>
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="qwen">Qwen</option>
        </select>

        {models.length > 0 && (
          <select value={model} onChange={e => setModel(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm mb-4">
            {models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        )}

        {message && (
          <p className={`text-sm mb-3 ${message.includes('failed') ? 'text-red-600' : 'text-green-600'}`}>
            {message}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100">Cancel</button>
          <button onClick={handleSwitch} disabled={switching || !provider || !model || (binding?.provider === provider && binding?.model === model)}
            className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50">
            {switching ? 'Switching...' : 'Switch'}
          </button>
        </div>
      </div>
    </div>
  )
}
