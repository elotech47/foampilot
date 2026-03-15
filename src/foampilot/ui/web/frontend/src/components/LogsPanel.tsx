import { useCallback, useEffect, useRef, useState } from 'react'

interface Props {
  running: boolean
}

type LogTab = 'case' | 'system'

function CopyIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
    </svg>
  )
}

const MIN_HEIGHT = 80
const MAX_HEIGHT = 700
const DEFAULT_HEIGHT = 280

export default function LogsPanel({ running }: Props) {
  const [tab, setTab] = useState<LogTab>('case')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [height, setHeight] = useState(DEFAULT_HEIGHT)
  const bottomRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const dragRef = useRef<{ startY: number; startH: number } | null>(null)

  const fetchLog = useCallback(async () => {
    try {
      const endpoint = tab === 'case' ? '/api/case-log' : '/api/system-log'
      const res = await fetch(endpoint)
      if (res.ok) {
        const json = await res.json() as { content: string }
        setContent(json.content)
      }
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
    }
  }, [tab])

  // Initial load + tab change
  useEffect(() => {
    setLoading(true)
    setContent('')
    void fetchLog()
  }, [fetchLog])

  // Poll while running
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (running) {
      intervalRef.current = setInterval(() => { void fetchLog() }, 2500)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [running, fetchLog])

  // Auto-scroll on content update
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'auto' })
    }
  }, [content])

  const handleCopy = () => {
    void navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  // ── Drag-to-resize ──────────────────────────────────────────────────────────

  const onDragStart = (e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startY: e.clientY, startH: height }

    const onMove = (me: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startY - me.clientY
      setHeight(Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, dragRef.current.startH + delta)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <div className="flex flex-col border-t border-[#1c2a3e] bg-[#070b14]" style={{ height: `${height}px` }}>
      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="h-1.5 w-full cursor-ns-resize bg-transparent hover:bg-teal-500/20 transition-colors shrink-0 flex items-center justify-center group"
        title="Drag to resize"
      >
        <div className="w-8 h-0.5 rounded-full bg-[#1c2a3e] group-hover:bg-teal-500/60 transition-colors" />
      </div>

      {/* Tab bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0d1117] border-b border-[#1c2a3e] shrink-0">
        <div className="flex items-center gap-0.5">
          {(['case', 'system'] as LogTab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
                tab === t
                  ? 'bg-teal-500/20 text-teal-400'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-[#162035]'
              }`}
            >
              {t === 'case' ? 'Case Log' : 'System Log'}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {running && (
            <span className="flex items-center gap-1 text-xs text-teal-500">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
              Live
            </span>
          )}
          <button
            onClick={handleCopy}
            className="btn-icon"
            title="Copy to clipboard"
          >
            {copied
              ? <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
              : <CopyIcon />
            }
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 min-h-0">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <svg className="w-5 h-5 text-slate-600 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          </div>
        ) : content ? (
          <>
            <pre className="text-[11px] font-mono text-slate-500 leading-relaxed whitespace-pre-wrap break-all">
              {content}
            </pre>
            <div ref={bottomRef} />
          </>
        ) : (
          <p className="text-xs text-slate-600 text-center mt-8">
            {tab === 'case' ? 'Case log will appear once a simulation starts.' : 'System log not available.'}
          </p>
        )}
      </div>
    </div>
  )
}
