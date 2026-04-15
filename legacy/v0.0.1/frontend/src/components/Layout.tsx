import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <Link to="/" className="text-lg font-semibold tracking-tight">
          Mnemonic
        </Link>
        <span className="text-xs text-gray-400">v1 — persistent research workspace</span>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  )
}
