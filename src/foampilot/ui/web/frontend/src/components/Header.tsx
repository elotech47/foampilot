import type { Phase, TokenInfo } from '../types'

interface Props {
  connected: boolean
  running: boolean
  phase: Phase
  sessionId: string | null
  tokenInfo: TokenInfo
}

const PHASE_META: Record<Phase, { label: string; color: string; dot: string }> = {
  idle:       { label: 'Idle',       color: 'text-slate-400 bg-slate-400/10 border-slate-700',    dot: 'bg-slate-500' },
  starting:   { label: 'Starting',   color: 'text-blue-400 bg-blue-400/10 border-blue-800',       dot: 'bg-blue-400 animate-pulse' },
  clarifying: { label: 'Clarifying', color: 'text-sky-400 bg-sky-400/10 border-sky-800',          dot: 'bg-sky-400 animate-pulse' },
  consulting: { label: 'Consulting', color: 'text-violet-400 bg-violet-400/10 border-violet-800', dot: 'bg-violet-400 animate-pulse' },
  setup:      { label: 'Setup',      color: 'text-amber-400 bg-amber-400/10 border-amber-800',    dot: 'bg-amber-400 animate-pulse' },
  meshing:    { label: 'Meshing',    color: 'text-orange-400 bg-orange-400/10 border-orange-800', dot: 'bg-orange-400 animate-pulse' },
  running:    { label: 'Running',    color: 'text-emerald-400 bg-emerald-400/10 border-emerald-800', dot: 'bg-emerald-400 animate-pulse' },
  analyzing:  { label: 'Analyzing', color: 'text-teal-400 bg-teal-400/10 border-teal-800',       dot: 'bg-teal-400 animate-pulse' },
  complete:   { label: 'Complete',   color: 'text-green-400 bg-green-400/10 border-green-800',    dot: 'bg-green-400' },
  error:      { label: 'Error',      color: 'text-red-400 bg-red-400/10 border-red-800',          dot: 'bg-red-500' },
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`
  return String(n)
}

export default function Header({ connected, running, phase, sessionId, tokenInfo }: Props) {
  const meta = PHASE_META[phase] ?? PHASE_META.idle

  return (
    <header className="flex items-center justify-between h-14 px-5 bg-[#0a0f1a] border-b border-[#1c2a3e] shrink-0 z-10">
      {/* Left: logo + session */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold">
            <span className="text-teal-400">foam</span>
            <span className="text-slate-100">Pilot</span>
          </span>
          <span className="text-slate-600 text-xs">CFD AI Agent</span>
        </div>

        {sessionId && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#111827] border border-[#1c2a3e]">
            <span className="text-slate-500 text-xs font-mono">session</span>
            <span className="text-slate-300 text-xs font-mono">{sessionId}</span>
          </div>
        )}
      </div>

      {/* Centre: phase badge */}
      <div className="flex items-center gap-3">
        <div
          className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${meta.color}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </div>

        {running && (
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <svg
              className="w-3 h-3 animate-spin text-teal-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <span className="text-teal-400">Processing</span>
          </div>
        )}
      </div>

      {/* Right: tokens + connection */}
      <div className="flex items-center gap-5">
        {tokenInfo.turns > 0 && (
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <span className="text-slate-600">in</span>
              <span className="text-slate-300 font-mono">{fmt(tokenInfo.inputTokens)}</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="text-slate-600">out</span>
              <span className="text-slate-300 font-mono">{fmt(tokenInfo.outputTokens)}</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="text-slate-600">cost</span>
              <span className="text-emerald-400 font-mono">${tokenInfo.costUsd.toFixed(3)}</span>
            </span>
            {tokenInfo.contextPct > 0 && (
              <span className="flex items-center gap-1">
                <span className="text-slate-600">ctx</span>
                <span
                  className={`font-mono ${
                    tokenInfo.contextPct > 80
                      ? 'text-red-400'
                      : tokenInfo.contextPct > 60
                      ? 'text-amber-400'
                      : 'text-slate-300'
                  }`}
                >
                  {tokenInfo.contextPct.toFixed(0)}%
                </span>
              </span>
            )}
          </div>
        )}

        {/* Connection indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? 'bg-emerald-400' : 'bg-red-500 animate-pulse'
            }`}
          />
          <span className="text-xs text-slate-500">{connected ? 'Connected' : 'Reconnecting…'}</span>
        </div>
      </div>
    </header>
  )
}
