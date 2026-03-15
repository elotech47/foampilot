import { useEffect, useRef, useState } from 'react'
import type { FileNode } from '../types'

interface Props {
  fileTree: FileNode | null
  running: boolean
  onRefresh: () => void
}

// ─── Icon helpers ────────────────────────────────────────────────────────────

function FolderIcon({ open }: { open: boolean }) {
  return open ? (
    <svg className="w-3.5 h-3.5 text-amber-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
      <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v1H2V6z" />
      <path d="M2 9h16v7a2 2 0 01-2 2H4a2 2 0 01-2-2V9z" />
    </svg>
  ) : (
    <svg className="w-3.5 h-3.5 text-amber-500/70 shrink-0" fill="currentColor" viewBox="0 0 20 20">
      <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
    </svg>
  )
}

function FileIcon({ name }: { name: string }) {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  const colorMap: Record<string, string> = {
    py: 'text-yellow-400',
    ts: 'text-blue-400',
    tsx: 'text-blue-400',
    json: 'text-green-400',
    log: 'text-slate-400',
    md: 'text-teal-400',
  }
  const color = colorMap[ext] ?? 'text-slate-500'
  return (
    <svg className={`w-3.5 h-3.5 ${color} shrink-0`} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  )
}

function ChevronRight() {
  return (
    <svg className="w-3 h-3 text-slate-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
    </svg>
  )
}

function ChevronDown() {
  return (
    <svg className="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  )
}

// ─── File Preview Modal ──────────────────────────────────────────────────────

function FilePreview({
  node,
  onClose,
}: {
  node: FileNode
  onClose: () => void
}) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!node.path) return
    fetch(`/api/file?path=${encodeURIComponent(node.path)}`)
      .then(r => r.json())
      .then((json: { content?: string; error?: string }) => {
        if (json.error) setError(json.error)
        else setContent(json.content ?? '')
      })
      .catch(() => setError('Failed to load file'))
  }, [node.path])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleCopy = () => {
    if (!content) return
    void navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex flex-col bg-[#0d1117] border border-[#1c2a3e] rounded-xl shadow-2xl w-[70vw] max-w-4xl h-[80vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1c2a3e] bg-[#070b14] shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <FileIcon name={node.name} />
            <span className="text-sm font-mono text-slate-300 truncate">{node.name}</span>
            {node.path && (
              <span className="text-[10px] text-slate-600 truncate hidden sm:block">{node.path}</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleCopy}
              disabled={!content}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs text-slate-500 hover:text-slate-300 hover:bg-[#162035] transition-colors disabled:opacity-30"
              title="Copy to clipboard"
            >
              {copied
                ? <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                : <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" /></svg>
              }
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-[#162035] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {content === null && !error && (
            <div className="flex items-center justify-center h-full">
              <svg className="w-6 h-6 text-slate-600 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
            </div>
          )}
          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}
          {content !== null && !error && (
            <pre className="text-[12px] font-mono text-slate-300 leading-relaxed whitespace-pre-wrap break-all">
              {content || <span className="text-slate-600 italic">Empty file</span>}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Tree node ───────────────────────────────────────────────────────────────

function TreeNode({
  node,
  depth = 0,
  onFileClick,
}: {
  node: FileNode
  depth?: number
  onFileClick: (node: FileNode) => void
}) {
  const [open, setOpen] = useState(depth < 2)
  const indent = depth * 12

  if (node.type === 'file') {
    return (
      <button
        className="flex items-center gap-1.5 w-full px-2 py-0.5 rounded hover:bg-[#162035] group text-left"
        style={{ paddingLeft: `${indent + 8}px` }}
        title={node.path}
        onClick={() => onFileClick(node)}
      >
        <FileIcon name={node.name} />
        <span className="text-xs text-slate-400 group-hover:text-slate-200 truncate transition-colors flex-1">
          {node.name}
        </span>
        {node.size !== undefined && (
          <span className="text-[10px] text-slate-600 shrink-0">
            {node.size < 1024 ? `${node.size}B` : `${(node.size / 1024).toFixed(0)}K`}
          </span>
        )}
      </button>
    )
  }

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 w-full px-2 py-0.5 rounded hover:bg-[#162035] group"
        style={{ paddingLeft: `${indent + 8}px` }}
      >
        <span className="w-3 shrink-0">{open ? <ChevronDown /> : <ChevronRight />}</span>
        <FolderIcon open={open} />
        <span className="text-xs text-slate-300 group-hover:text-slate-100 truncate transition-colors">
          {node.name}
        </span>
      </button>

      {open && node.children && (
        <div>
          {node.children.map(child => (
            <TreeNode key={child.path ?? child.name} node={child} depth={depth + 1} onFileClick={onFileClick} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export default function FilePanel({ fileTree, running, onRefresh }: Props) {
  const [previewNode, setPreviewNode] = useState<FileNode | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  return (
    <div ref={containerRef} className="panel w-56 shrink-0 border-r border-[#1c2a3e]">
      <div className="panel-header">
        <span className="panel-title">File Explorer</span>
        <button
          onClick={onRefresh}
          className="btn-icon"
          title="Refresh"
          disabled={!running && !fileTree}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {fileTree ? (
          <TreeNode node={fileTree} depth={0} onFileClick={node => setPreviewNode(node)} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 px-4 text-center">
            <svg className="w-10 h-10 text-slate-700" fill="none" stroke="currentColor" strokeWidth={1} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
            <p className="text-xs text-slate-600 leading-relaxed">
              {running ? 'Case directory will appear here once setup begins.' : 'No active simulation.'}
            </p>
          </div>
        )}
      </div>

      {previewNode && (
        <FilePreview node={previewNode} onClose={() => setPreviewNode(null)} />
      )}
    </div>
  )
}
