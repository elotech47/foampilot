import { useEffect, useRef, useState } from 'react'
import type { AgentEvent, Phase } from '../types'
import LogsPanel from './LogsPanel'

interface Props {
  events: AgentEvent[]
  logsOpen: boolean
  onToggleLogs: () => void
  running: boolean
}

// ─── Phase styling ────────────────────────────────────────────────────────────

const PHASE_STYLE: Record<Phase, { label: string; bar: string; text: string; bg: string }> = {
  idle:       { label: 'Idle',       bar: 'bg-slate-600',    text: 'text-slate-400',   bg: 'bg-slate-900/30' },
  starting:   { label: 'Starting',   bar: 'bg-blue-500',     text: 'text-blue-400',    bg: 'bg-blue-950/30' },
  clarifying: { label: 'Clarifying', bar: 'bg-sky-500',      text: 'text-sky-400',     bg: 'bg-sky-950/30' },
  consulting: { label: 'Consulting', bar: 'bg-violet-500',   text: 'text-violet-400',  bg: 'bg-violet-950/30' },
  setup:      { label: 'Setup',      bar: 'bg-amber-500',    text: 'text-amber-400',   bg: 'bg-amber-950/30' },
  meshing:    { label: 'Meshing',    bar: 'bg-orange-500',   text: 'text-orange-400',  bg: 'bg-orange-950/30' },
  running:    { label: 'Running',    bar: 'bg-emerald-500',  text: 'text-emerald-400', bg: 'bg-emerald-950/30' },
  analyzing:  { label: 'Analyzing', bar: 'bg-teal-500',     text: 'text-teal-400',    bg: 'bg-teal-950/30' },
  complete:   { label: 'Complete',   bar: 'bg-green-500',    text: 'text-green-400',   bg: 'bg-green-950/30' },
  error:      { label: 'Error',      bar: 'bg-red-500',      text: 'text-red-400',     bg: 'bg-red-950/30' },
}

// ─── Phase divider ────────────────────────────────────────────────────────────

function PhaseEvent({ phase }: { phase: Phase }) {
  const s = PHASE_STYLE[phase] ?? PHASE_STYLE.idle
  return (
    <div className={`flex items-center gap-3 px-4 py-2 my-1 rounded ${s.bg}`}>
      <span className={`w-1 h-4 rounded-full ${s.bar}`} />
      <span className={`text-sm font-semibold tracking-widest uppercase ${s.text}`}>
        {s.label}
      </span>
      <span className="flex-1 h-px bg-current opacity-10" />
    </div>
  )
}

// ─── Tool call card ───────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: 'pending' | 'success' | 'error' }) {
  if (status === 'pending') {
    return (
      <svg className="w-4 h-4 text-blue-400 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
      </svg>
    )
  }
  if (status === 'success') {
    return (
      <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  }
  return (
    <svg className="w-4 h-4 text-red-400 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

function summariseInput(input: Record<string, unknown>): string {
  const entries = Object.entries(input)
  if (entries.length === 0) return '—'
  const first = entries.slice(0, 2).map(([k, v]) => {
    const val = typeof v === 'string' ? v.slice(0, 40) : JSON.stringify(v).slice(0, 40)
    return `${k}: ${val}`
  })
  return first.join(' · ') + (entries.length > 2 ? ` +${entries.length - 2} more` : '')
}

function ToolCard({ event }: { event: AgentEvent }) {
  const [expanded, setExpanded] = useState(false)
  const tc = event.toolCall!

  const borderColor =
    tc.status === 'success' ? 'border-emerald-900/50' :
    tc.status === 'error'   ? 'border-red-900/50' :
                              'border-blue-900/50'

  return (
    <div className={`mx-4 my-1 rounded-lg border ${borderColor} bg-[#0d1117] overflow-hidden`}>
      <button
        className="flex items-center gap-2.5 w-full px-3 py-2 text-left hover:bg-[#131b2a] transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <StatusIcon status={tc.status} />

        <span className="font-mono text-sm text-slate-200 font-medium">{tc.tool}</span>

        <span className="flex-1 text-sm text-slate-500 truncate">{summariseInput(tc.input)}</span>

        <svg
          className={`w-3.5 h-3.5 text-slate-600 transition-transform shrink-0 ${expanded ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-[#1c2a3e] px-3 py-2 space-y-2">
          <div>
            <p className="text-xs text-slate-600 font-semibold tracking-wider uppercase mb-1">Input</p>
            <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap break-all leading-relaxed">
              {JSON.stringify(tc.input, null, 2).slice(0, 2000)}
            </pre>
          </div>

          {tc.status !== 'pending' && (
            <div>
              <p className={`text-xs font-semibold tracking-wider uppercase mb-1 ${
                tc.status === 'success' ? 'text-emerald-600' : 'text-red-600'
              }`}>
                {tc.status === 'success' ? 'Result' : 'Error'}
              </p>
              <pre className={`text-xs font-mono whitespace-pre-wrap break-all leading-relaxed ${
                tc.status === 'success' ? 'text-slate-400' : 'text-red-400'
              }`}>
                {tc.status === 'success'
                  ? JSON.stringify(tc.result, null, 2)?.slice(0, 2000)
                  : tc.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── LLM reasoning block ──────────────────────────────────────────────────────

function LLMBlock({ event }: { event: AgentEvent }) {
  const [expanded, setExpanded] = useState(false)
  const lr = event.llmResponse!
  const preview = lr.text.slice(0, 160)
  const hasMore = lr.text.length > 160

  return (
    <div className="mx-4 my-1 rounded-lg border border-[#1c2a3e] bg-[#0d1117] overflow-hidden">
      <button
        className="flex items-start gap-2.5 w-full px-3 py-2 text-left hover:bg-[#131b2a] transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <svg
          className="w-3.5 h-3.5 text-violet-500 shrink-0 mt-0.5"
          fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs text-violet-500 font-semibold tracking-wider uppercase">
              Reasoning
            </span>
            <span className="text-xs text-slate-600">turn {lr.turn}</span>
          </div>
          <p className="text-sm text-slate-400 line-clamp-2 leading-relaxed">
            {preview}{!expanded && hasMore ? '…' : ''}
          </p>
        </div>

        {hasMore && (
          <svg
            className={`w-3.5 h-3.5 text-slate-600 transition-transform shrink-0 mt-0.5 ${expanded ? 'rotate-180' : ''}`}
            fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        )}
      </button>

      {expanded && hasMore && (
        <div className="border-t border-[#1c2a3e] px-3 py-2">
          <p className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap">{lr.text}</p>
        </div>
      )}
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
      <svg
        className="w-14 h-14 text-slate-800"
        fill="none" stroke="currentColor" strokeWidth={0.75} viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
      </svg>
      <div>
        <p className="text-base text-slate-500 font-medium mb-1">Agent process will appear here</p>
        <p className="text-sm text-slate-600 leading-relaxed">
          Start a simulation from the chat panel to see reasoning, tool calls, and phase progression in real time.
        </p>
      </div>
    </div>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export default function AgentPanel({ events, logsOpen, onToggleLogs, running }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events.length])

  return (
    <div className="panel flex-1 border-x border-[#1c2a3e]">
      {/* Header */}
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span className="panel-title">Agent Process</span>
          {running && (
            <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
          )}
          {events.length > 0 && (
            <span className="text-xs text-slate-600">{events.length} events</span>
          )}
        </div>

        <button
          onClick={onToggleLogs}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            logsOpen
              ? 'bg-teal-500/20 text-teal-400 border border-teal-800'
              : 'text-slate-500 hover:text-slate-300 hover:bg-[#162035] border border-transparent'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          Logs
        </button>
      </div>

      {/* Events area + optional logs split */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Event stream */}
        <div className="flex-1 overflow-y-auto py-2">
          {events.length === 0 && !running ? (
            <EmptyState />
          ) : (
            <>
              {events.length === 0 && running && (
                <div className="flex flex-col items-center justify-center h-48 gap-4">
                  <div className="flex gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-teal-400 animate-bounce [animation-delay:0ms]" />
                    <span className="w-2 h-2 rounded-full bg-teal-400 animate-bounce [animation-delay:150ms]" />
                    <span className="w-2 h-2 rounded-full bg-teal-400 animate-bounce [animation-delay:300ms]" />
                  </div>
                  <p className="text-xs text-slate-500">Agent initialising…</p>
                </div>
              )}
              {events.map(event => {
                if (event.kind === 'phase') {
                  return <PhaseEvent key={event.id} phase={event.phase!} />
                }
                if (event.kind === 'tool') {
                  return <ToolCard key={event.id} event={event} />
                }
                if (event.kind === 'llm') {
                  return <LLMBlock key={event.id} event={event} />
                }
                return null
              })}
              {running && events.length > 0 && (
                <div className="flex items-center gap-2 mx-4 my-2 text-slate-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse" />
                  <span className="text-xs">Processing…</span>
                </div>
              )}
              <div ref={bottomRef} className="h-2" />
            </>
          )}
        </div>

        {/* Logs panel (collapsible) */}
        {logsOpen && (
          <LogsPanel running={running} />
        )}
      </div>
    </div>
  )
}
