/**
 * LogViewer — terminal-style log display
 * Colore INFO (vert), WARN (amber), ERROR (rouge), DEBUG (bleu).
 * Auto-scroll au dernier log. Bouton copy-to-clipboard.
 */
import { useEffect, useRef, useState } from 'react'
import { Copy, Check, Terminal } from 'lucide-react'

interface Props {
  lines: string[]
  maxHeight?: number   // px, défaut 320
  title?: string
}

type Level = 'error' | 'warn' | 'info' | 'debug' | 'plain'

function detectLevel(line: string): Level {
  const u = line.toUpperCase()
  if (u.includes('ERROR') || u.includes('FAILED') || u.includes('✗') || u.includes('EXCEPTION')) return 'error'
  if (u.includes('WARN') || u.includes('WARNING') || u.includes('⚠') || u.includes('SKIP')) return 'warn'
  if (u.includes('DEBUG')) return 'debug'
  if (u.includes('INFO') || u.includes('✓') || u.includes('✅') || u.includes('START')) return 'info'
  return 'plain'
}

const LEVEL_COLORS: Record<Level, string> = {
  error: '#f87171',   // red-400
  warn:  '#fbbf24',   // amber-400
  info:  '#34d399',   // emerald-400
  debug: '#60a5fa',   // blue-400
  plain: '#94a3b8',   // slate-400
}

function LogLine({ line }: { line: string }) {
  const level = detectLevel(line)
  const color = LEVEL_COLORS[level]

  // Mettre en évidence le préfixe de niveau
  const highlighted = line.replace(
    /^(INFO|WARN|WARNING|ERROR|DEBUG)\s/,
    (m) => `<span style="color:${color};font-weight:600">${m}</span>`
  )

  return (
    <div
      className="leading-5 whitespace-pre-wrap break-all"
      style={{ color }}
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  )
}

export default function LogViewer({ lines, maxHeight = 320, title }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied]     = useState(false)
  const [follow, setFollow]     = useState(true)

  // Auto-scroll si follow est actif
  useEffect(() => {
    if (follow) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, follow])

  const copy = () => {
    navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (lines.length === 0) {
    return (
      <div className="rounded-lg px-4 py-3 text-xs font-mono flex items-center gap-2"
        style={{ background: '#0a0a0a', color: '#64748b', border: '1px solid var(--bg-border)' }}>
        <Terminal size={12} /> No logs captured.
      </div>
    )
  }

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--bg-border)' }}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5"
        style={{ background: '#111', borderBottom: '1px solid #1f1f1f' }}>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#ef4444' }} />
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#f59e0b' }} />
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#10b981' }} />
          </div>
          {title && <span className="text-xs font-mono" style={{ color: '#64748b' }}>{title}</span>}
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none"
            style={{ color: '#64748b' }}>
            <input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)}
              className="w-3 h-3 accent-emerald-500" />
            Follow
          </label>
          <button onClick={copy}
            className="flex items-center gap-1 text-xs px-2 py-0.5 rounded transition-opacity hover:opacity-70"
            style={{ background: '#1f1f1f', color: '#94a3b8' }}>
            {copied ? <><Check size={10} /> Copied</> : <><Copy size={10} /> Copy</>}
          </button>
        </div>
      </div>

      {/* Log content */}
      <div
        className="overflow-y-auto p-3 font-mono text-xs space-y-0.5"
        style={{ background: '#0a0a0a', maxHeight }}
        onScroll={e => {
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 20
          setFollow(atBottom)
        }}
      >
        {lines.map((line, i) => <LogLine key={i} line={line} />)}
        <div ref={bottomRef} />
      </div>

      {/* Footer: line count */}
      <div className="px-3 py-1 text-xs" style={{ background: '#111', color: '#475569', borderTop: '1px solid #1f1f1f' }}>
        {lines.length} line{lines.length !== 1 ? 's' : ''}
      </div>
    </div>
  )
}
