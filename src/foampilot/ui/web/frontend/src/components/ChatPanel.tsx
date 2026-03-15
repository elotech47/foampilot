import { useEffect, useRef, useState } from 'react'
import type { ChatMessage, ClarificationData } from '../types'

interface Props {
  messages: ChatMessage[]
  running: boolean
  approvalPending: boolean
  clarificationPending: boolean
  autoApprove: boolean
  sessionDone: boolean
  width: number
  onWidthChange: (w: number) => void
  onStart: (prompt: string) => void
  onStop: () => void
  onNewSession: () => void
  onApprove: (approved: boolean) => void
  onSetAutoApprove: (enabled: boolean) => void
}

const MIN_WIDTH = 320
const MAX_WIDTH = 960

// ─── Individual message components ───────────────────────────────────────────

function UserMessage({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex justify-end mb-3">
      <div className="max-w-[85%]">
        <div className="bg-blue-600/20 border border-blue-800/50 rounded-2xl rounded-tr-sm px-4 py-2.5">
          <p className="text-[15px] text-slate-200 leading-relaxed whitespace-pre-wrap">{msg.text}</p>
        </div>
        <p className="text-right text-xs text-slate-600 mt-0.5 pr-1">
          {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

function SystemMessage({ msg }: { msg: ChatMessage }) {
  const isError = msg.text.toLowerCase().startsWith('error')
  const isComplete = msg.text.toLowerCase().includes('complete')

  return (
    <div className="flex justify-center mb-2">
      <div
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border ${
          isError
            ? 'text-red-400 bg-red-950/30 border-red-900/50'
            : isComplete
            ? 'text-green-400 bg-green-950/30 border-green-900/50'
            : 'text-slate-500 bg-slate-900/50 border-slate-800'
        }`}
      >
        {msg.text}
      </div>
    </div>
  )
}

// ─── Clarification card ──────────────────────────────────────────────────────

function ClarificationCard({
  msg,
  isActive,
  onAnswer,
}: {
  msg: ChatMessage
  isActive: boolean
  onAnswer: (text: string) => void
}) {
  const [inputVal, setInputVal] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const data = msg.clarificationData as ClarificationData | null

  useEffect(() => {
    if (isActive && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isActive])

  // Answered state — show read-only summary
  if (msg.answered) {
    return (
      <div className="mb-3">
        <div className="rounded-xl border border-slate-800/50 bg-slate-900/20 overflow-hidden opacity-70">
          <div className="px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1">
              <svg className="w-3 h-3 text-cyan-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
              <span className="text-[10px] text-cyan-600 font-semibold tracking-wider uppercase">FoamPilot asked</span>
            </div>
            <p className="text-xs text-slate-500 line-clamp-2">
              {data?.question ?? msg.text}
            </p>
          </div>
          {msg.clarificationParams && Object.keys(msg.clarificationParams).length > 0 && (
            <div className="px-3 pb-2 border-t border-slate-800/30 pt-1.5 space-y-0.5">
              {Object.entries(msg.clarificationParams).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-[11px]">
                  <span className="text-slate-600 min-w-[80px] shrink-0">{k}</span>
                  <span className="text-slate-400 font-mono">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  // No structured data — plain text fallback
  if (!data) {
    return (
      <div className="flex justify-start mb-3">
        <div className="max-w-[90%]">
          <div className="flex items-center gap-1.5 mb-1.5">
            <svg className="w-3 h-3 text-cyan-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
            <span className="text-[10px] text-cyan-500 font-semibold tracking-wider uppercase">FoamPilot</span>
          </div>
          <div className="bg-cyan-950/20 border border-cyan-800/40 rounded-2xl rounded-tl-sm px-4 py-2.5">
            <p className="text-[15px] text-slate-200 leading-relaxed whitespace-pre-wrap">{msg.text}</p>
          </div>
        </div>
      </div>
    )
  }

  const handleSubmit = () => {
    const val = selected ?? inputVal.trim()
    if (!val && !data.default) return
    onAnswer(val || data.default || '')
    setSelected(null)
    setInputVal('')
  }

  const handleSelect = (opt: string) => {
    setSelected(prev => prev === opt ? null : opt)
    setInputVal('')
  }

  return (
    <div className="mb-3">
      {/* Agent label */}
      <div className="flex items-center gap-1.5 mb-1.5 px-1">
        <svg className="w-3 h-3 text-cyan-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>
        <span className="text-[10px] text-cyan-500 font-semibold tracking-wider uppercase">FoamPilot</span>
        {data.parameter && (
          <span className="text-[10px] text-slate-600 font-mono">· {data.parameter}</span>
        )}
      </div>

      <div className={`rounded-xl border overflow-hidden transition-colors ${
        isActive ? 'border-cyan-700/60 shadow-lg shadow-cyan-950/30' : 'border-cyan-800/30'
      } bg-[#0a1020]`}>

        {/* Context */}
        {data.context && (
          <div className="px-3 pt-3 pb-1">
            <p className="text-sm text-slate-500 leading-relaxed">{data.context}</p>
          </div>
        )}

        {/* Question */}
          <div className="px-3 py-2.5">
          <p className="text-[15px] text-slate-100 font-medium leading-snug">{data.question}</p>
          {data.hint && (
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{data.hint}</p>
          )}
        </div>

        {/* Options */}
        {data.options && data.options.length > 0 && (
          <div className="px-3 pb-2 flex flex-wrap gap-1.5">
            {data.options.map(opt => {
              const isSelected = selected === opt
              return (
                <button
                  key={opt}
                  onClick={() => handleSelect(opt)}
                  disabled={!isActive}
                  className={`px-3 py-2 rounded-lg text-sm border transition-all disabled:cursor-not-allowed ${
                    isSelected
                      ? 'bg-cyan-500/25 border-cyan-500/70 text-cyan-200 shadow-sm shadow-cyan-900/30'
                      : 'bg-[#0d1420] border-[#1c2a3e] text-slate-400 hover:border-cyan-800/70 hover:text-slate-200 hover:bg-cyan-950/20'
                  }`}
                >
                  {opt}
                </button>
              )
            })}
          </div>
        )}

        {/* Text input */}
        {isActive && (
          <div className="px-3 pb-3 flex gap-2 items-center">
            <input
              ref={inputRef}
              type="text"
              value={inputVal}
              onChange={e => { setInputVal(e.target.value); setSelected(null) }}
              onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
              placeholder={
                selected
                  ? `"${selected}" selected`
                  : data.default
                  ? `Default: ${data.default}`
                  : data.options
                  ? 'Or type a custom value…'
                  : 'Type your answer…'
              }
              className={`flex-1 bg-[#0d1117] border rounded-lg px-3 py-2 text-[15px] text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors ${
                selected ? 'border-[#1c2a3e] opacity-50' : 'border-[#1c2a3e] hover:border-cyan-800/50'
              }`}
            />
            <button
              onClick={handleSubmit}
              disabled={!selected && !inputVal.trim() && !data.default}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600/30 border border-cyan-700/50 text-cyan-300 hover:bg-cyan-600/50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
            >
              Send
            </button>
          </div>
        )}

        {/* Default hint */}
        {data.default && isActive && (
          <p className="px-3 pb-2.5 text-[10px] text-slate-600">
            Press Send without typing to use default: <span className="font-mono text-slate-500">{data.default}</span>
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Confirm params card ──────────────────────────────────────────────────────

function ConfirmParamsCard({
  msg,
  isActive,
  onAnswer,
}: {
  msg: ChatMessage
  isActive: boolean
  onAnswer: (text: string) => void
}) {
  const params = msg.clarificationParams

  if (msg.answered) {
    return (
      <div className="flex justify-center mb-2">
        <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs border text-green-400 bg-green-950/30 border-green-900/50">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Parameters confirmed — starting simulation
        </div>
      </div>
    )
  }

  return (
    <div className="mb-3">
      <div className="rounded-xl border border-green-800/50 bg-green-950/10 overflow-hidden">
        <div className="px-3 py-2 bg-green-900/15 border-b border-green-800/20 flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-xs text-green-400 font-semibold">All parameters confirmed</span>
        </div>
        {params && Object.keys(params).length > 0 && (
          <div className="px-3 py-2 space-y-1.5">
            {Object.entries(params).map(([k, v]) => (
              <div key={k} className="flex gap-3 text-sm">
                <span className="text-slate-500 min-w-[120px] shrink-0">{k}</span>
                <span className="text-slate-300 font-mono">{String(v)}</span>
              </div>
            ))}
          </div>
        )}
        {isActive && (
          <div className="px-3 pb-3 flex gap-2">
            <button
              onClick={() => onAnswer('go')}
              className="flex-1 py-2 rounded-lg text-sm font-semibold bg-green-600/30 border border-green-700/50 text-green-300 hover:bg-green-600/50 transition-colors"
            >
              Confirm & Start Simulation
            </button>
            <button
              onClick={() => onAnswer('cancel')}
              className="px-3 py-2 rounded-lg text-sm text-slate-500 hover:text-slate-300 hover:bg-[#162035] border border-[#1c2a3e] transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Approval card ────────────────────────────────────────────────────────────

function ApprovalCard({
  msg,
  onApprove,
  onSetAutoApprove,
}: {
  msg: ChatMessage
  onApprove: (approved: boolean) => void
  onSetAutoApprove: (enabled: boolean) => void
}) {
  if (msg.resolved) {
    return (
      <div className="mb-3 mx-1">
        <div
          className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs ${
            msg.approved
              ? 'bg-emerald-950/20 border-emerald-900/40 text-emerald-500'
              : 'bg-red-950/20 border-red-900/40 text-red-500'
          }`}
        >
          {msg.approved ? (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
          <span>{msg.approved ? 'Approved' : 'Denied'}: <code className="font-mono">{msg.approvalTool}</code></span>
        </div>
      </div>
    )
  }

  return (
    <div className="mb-3 mx-1">
      <div className="rounded-xl border border-amber-800/60 bg-amber-950/20 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-900/20 border-b border-amber-800/30">
          <svg className="w-3.5 h-3.5 text-amber-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
          <span className="text-xs text-amber-400 font-semibold">Permission Required</span>
        </div>
        <div className="px-3 py-2.5 space-y-2">
          <p className="text-sm text-slate-300">
            The agent wants to run:{' '}
            <code className="font-mono text-amber-300 bg-amber-900/30 px-1.5 py-0.5 rounded">
              {msg.approvalTool}
            </code>
          </p>
          {msg.approvalInput && Object.keys(msg.approvalInput).length > 0 && (
            <pre className="text-xs font-mono text-slate-500 bg-[#070b14] rounded p-2 max-h-28 overflow-y-auto">
              {JSON.stringify(msg.approvalInput, null, 2).slice(0, 600)}
            </pre>
          )}
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => onApprove(true)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-600/30 border border-emerald-700/50 text-emerald-400 text-sm font-medium hover:bg-emerald-600/50 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              Approve
            </button>
            <button
              onClick={() => onApprove(false)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-red-600/20 border border-red-800/50 text-red-400 text-sm font-medium hover:bg-red-600/30 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
              Deny
            </button>
          </div>
          <button
            onClick={() => { onSetAutoApprove(true); onApprove(true) }}
            className="w-full py-1 text-xs text-slate-500 hover:text-amber-400 transition-colors"
          >
            Approve this & enable Auto-approve for session
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 px-6 text-center">
      <svg className="w-12 h-12 text-slate-800" fill="none" stroke="currentColor" strokeWidth={0.75} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
      </svg>
      <div>
        <p className="text-base text-slate-500 font-medium mb-1">Start a simulation</p>
        <p className="text-sm text-slate-600 leading-relaxed">
          Describe your CFD simulation — FoamPilot will ask clarifying questions before setting up the case.
        </p>
      </div>
    </div>
  )
}

// ─── Input area ───────────────────────────────────────────────────────────────

function InputArea({
  running,
  approvalPending,
  clarificationPending,
  autoApprove,
  sessionDone,
  onStart,
  onStop,
  onNewSession,
  onSetAutoApprove,
}: {
  running: boolean
  approvalPending: boolean
  clarificationPending: boolean
  autoApprove: boolean
  sessionDone: boolean
  onStart: (prompt: string) => void
  onStop: () => void
  onNewSession: () => void
  onSetAutoApprove: (enabled: boolean) => void
}) {
  const [text, setText] = useState('')

  if (clarificationPending) return null

  const canSend = text.trim().length > 0 && !running

  const handleSend = () => {
    if (!canSend) return
    onStart(text.trim())
    setText('')
  }

  return (
    <div className="shrink-0 border-t border-[#1c2a3e] bg-[#0a0f1a] p-3 space-y-2">
      <div className="flex items-center justify-between px-1">
        <span className="text-sm text-slate-600">
          {approvalPending ? '⚠ Awaiting your approval above' : running ? 'Simulation in progress…' : 'Describe your simulation'}
        </span>
        <div className="flex items-center gap-3">
          {running && (
            <button
              onClick={onStop}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-900/30 border border-red-800/50 text-red-400 hover:bg-red-900/50 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
              Stop
            </button>
          )}
          {sessionDone && !running && (
            <button
              onClick={onNewSession}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-teal-900/30 border border-teal-800/50 text-teal-400 hover:bg-teal-900/50 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              New Session
            </button>
          )}
          <label className="flex items-center gap-2 cursor-pointer group">
            <span className="text-sm text-slate-500 group-hover:text-slate-400 transition-colors">Auto-approve</span>
            <button
              onClick={() => onSetAutoApprove(!autoApprove)}
              className={`relative w-9 h-5 rounded-full transition-colors ${autoApprove ? 'bg-teal-500' : 'bg-slate-700'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${autoApprove ? 'translate-x-4' : ''}`} />
            </button>
          </label>
        </div>
      </div>
      <div className="flex gap-2 items-end">
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          placeholder={running ? 'Simulation in progress…' : 'e.g. Simulate lid-driven cavity flow at Re=100'}
          disabled={running}
          rows={3}
          className={`w-full resize-none rounded-xl px-3.5 py-2.5 text-[15px] leading-relaxed bg-[#0d1117] border text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-teal-500/50 transition-colors ${
            running ? 'border-[#1c2a3e] opacity-50 cursor-not-allowed' : 'border-[#1c2a3e] hover:border-[#243449]'
          }`}
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          className={`flex items-center justify-center w-10 h-10 rounded-xl transition-all mb-0.5 ${
            canSend ? 'bg-teal-500 hover:bg-teal-400 text-white shadow-lg shadow-teal-900/40' : 'bg-[#111827] text-slate-600 cursor-not-allowed border border-[#1c2a3e]'
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
          </svg>
        </button>
      </div>
      <p className="text-xs text-slate-700 px-1">Enter to send · Shift+Enter for new line</p>
    </div>
  )
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export default function ChatPanel({
  messages,
  running,
  approvalPending,
  clarificationPending,
  autoApprove,
  sessionDone,
  width,
  onWidthChange,
  onStart,
  onStop,
  onNewSession,
  onApprove,
  onSetAutoApprove,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length])

  // ── Resize drag handle ───────────────────────────────────────────────────
  const onDragStart = (e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: width }
    const onMove = (me: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startX - me.clientX
      onWidthChange(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, dragRef.current.startW + delta)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  // Last unanswered clarification index
  const lastUnansweredIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'clarification' && !messages[i].answered) return i
    }
    return -1
  })()

  return (
    <div className="panel shrink-0 border-l border-[#1c2a3e] flex" style={{ width: `${width}px` }}>
      {/* Drag handle — left edge */}
      <div
        onMouseDown={onDragStart}
        className="w-1 shrink-0 cursor-ew-resize hover:bg-teal-500/30 transition-colors group"
        title="Drag to resize"
      />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="panel-header">
          <span className="panel-title">Simulation</span>
          <div className="flex items-center gap-2">
            {approvalPending && (
              <span className="flex items-center gap-1 text-xs text-amber-400 animate-pulse">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
                </svg>
                Approval needed
              </span>
            )}
            {clarificationPending && !approvalPending && (
              <span className="flex items-center gap-1 text-xs text-cyan-400 animate-pulse">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
                </svg>
                Clarifying
              </span>
            )}
            {running && (
              <button
                onClick={onStop}
                title="Stop simulation"
                className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-900/30 border border-red-800/50 text-red-400 hover:bg-red-900/50 transition-colors"
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
                Stop
              </button>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-3">
          {messages.length === 0 ? (
            <EmptyState />
          ) : (
            <>
              {messages.map((msg, idx) => {
                if (msg.role === 'user') return <UserMessage key={msg.id} msg={msg} />
                if (msg.role === 'clarification') {
                  // If it has clarificationParams (confirm state), show confirm card
                  if (msg.clarificationParams && Object.keys(msg.clarificationParams).length > 0 && !msg.clarificationData) {
                    return (
                      <ConfirmParamsCard
                        key={msg.id}
                        msg={msg}
                        isActive={idx === lastUnansweredIdx}
                        onAnswer={onStart}
                      />
                    )
                  }
                  return (
                    <ClarificationCard
                      key={msg.id}
                      msg={msg}
                      isActive={idx === lastUnansweredIdx}
                      onAnswer={onStart}
                    />
                  )
                }
                if (msg.role === 'approval') {
                  return (
                    <ApprovalCard
                      key={msg.id}
                      msg={msg}
                      onApprove={onApprove}
                      onSetAutoApprove={onSetAutoApprove}
                    />
                  )
                }
                return <SystemMessage key={msg.id} msg={msg} />
              })}
              {running && !approvalPending && !clarificationPending && (
                <div className="flex items-end gap-2 mb-3">
                  <div className="bg-[#111827] border border-[#1c2a3e] rounded-2xl rounded-bl-sm px-4 py-3">
                    <div className="flex gap-1 items-center">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce [animation-delay:0ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce [animation-delay:150ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce [animation-delay:300ms]" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </>
          )}
        </div>

        {/* Input area — hidden during clarification (cards handle input) */}
        <InputArea
          running={running}
          approvalPending={approvalPending}
          clarificationPending={clarificationPending}
          autoApprove={autoApprove}
          sessionDone={sessionDone}
          onStart={onStart}
          onStop={onStop}
          onNewSession={onNewSession}
          onSetAutoApprove={onSetAutoApprove}
        />
      </div>
    </div>
  )
}
