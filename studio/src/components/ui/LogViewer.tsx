/**
 * LogViewer — terminal-style log display
 * Colore INFO (vert), WARN (amber), ERROR (rouge), DEBUG (bleu).
 * Auto-scroll au dernier log. Bouton copy-to-clipboard.
 * Menu contextuel (clic droit) : Clear / Copy / Save…
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

function defaultLogName(title?: string): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  const base = (title ?? 'run').replace(/[^A-Za-z0-9_-]+/g, '_')
  return `logs_${base}_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.log`
}

export default function LogViewer({ lines, maxHeight = 320, title }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied]     = useState(false)
  const [follow, setFollow]     = useState(true)
  const [clearedCount, setClearedCount] = useState(0)
  const [ctxMenu, setCtxMenu]   = useState<{ x: number; y: number } | null>(null)
  const [saveDialog, setSaveDialog] = useState(false)
  const [fileName, setFileName] = useState('')

  // Lignes visibles après un éventuel Clear local
  const visible = clearedCount > 0 ? lines.slice(clearedCount) : lines

  // Nouveau run (le flux de lignes repart de zéro ou raccourcit) → reset Clear
  useEffect(() => {
    if (lines.length < clearedCount) setClearedCount(0)
  }, [lines, clearedCount])

  // Auto-scroll si follow est actif
  useEffect(() => {
    if (follow) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, follow])

  // Fermer le menu contextuel au clic ailleurs / Échap
  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setCtxMenu(null) }
    window.addEventListener('click', close)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', onKey) }
  }, [ctxMenu])

  const copy = () => {
    navigator.clipboard.writeText(visible.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const doClear = () => { setClearedCount(lines.length); setCtxMenu(null) }

  const doCopy = async () => {
    const sel = window.getSelection()?.toString()
    const text = sel && sel.trim() ? sel : visible.join('\n')
    try { await navigator.clipboard.writeText(text) } catch { /* clipboard indisponible */ }
    setCtxMenu(null)
  }

  const doSave = () => {
    setFileName(defaultLogName(title))
    setSaveDialog(true)
    setCtxMenu(null)
  }

  const confirmSave = () => {
    const name = fileName.trim() || defaultLogName(title)
    const blob = new Blob([visible.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' })
    const url  = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name.includes('.') ? name : `${name}.log`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    setSaveDialog(false)
  }

  const menuItemStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
    padding: '6px 14px', background: 'transparent', border: 'none',
    color: '#c9d1d9', fontSize: 12, cursor: 'pointer', textAlign: 'left',
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
    <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--bg-border)', position: 'relative' }}>
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
        onContextMenu={e => {
          e.preventDefault()
          const host = e.currentTarget.closest('.rounded-lg')!.getBoundingClientRect()
          setCtxMenu({ x: e.clientX - host.left, y: e.clientY - host.top })
        }}
      >
        {visible.length === 0
          ? <div style={{ color: '#475569' }}>— cleared —</div>
          : visible.map((line, i) => <LogLine key={i} line={line} />)}
        <div ref={bottomRef} />
      </div>

      {/* Footer: line count */}
      <div className="px-3 py-1 text-xs" style={{ background: '#111', color: '#475569', borderTop: '1px solid #1f1f1f' }}>
        {visible.length} line{visible.length !== 1 ? 's' : ''}
      </div>

      {/* Menu contextuel : Clear / Copy / Save */}
      {ctxMenu && (
        <div
          style={{
            position: 'absolute', left: ctxMenu.x, top: ctxMenu.y, zIndex: 50,
            background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)', padding: '4px 0', minWidth: 150,
          }}
          onClick={e => e.stopPropagation()}
        >
          <button style={menuItemStyle} onClick={doClear}
            onMouseEnter={e => (e.currentTarget.style.background = '#21262d')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
            🧹 Clear
          </button>
          <button style={menuItemStyle} onClick={doCopy}
            onMouseEnter={e => (e.currentTarget.style.background = '#21262d')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
            📋 Copy
          </button>
          <button style={menuItemStyle} onClick={doSave}
            onMouseEnter={e => (e.currentTarget.style.background = '#21262d')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
            💾 Save…
          </button>
        </div>
      )}

      {/* Boîte de dialogue Save : nom du fichier log */}
      {saveDialog && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 60, display: 'flex',
          alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)',
        }}>
          <div style={{
            background: '#161b22', border: '1px solid #30363d', borderRadius: 10,
            padding: 18, width: 380, boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#c9d1d9', marginBottom: 10 }}>
              Sauvegarder les logs
            </div>
            <label style={{ display: 'block', fontSize: 11, color: '#8b949e', marginBottom: 4 }}>
              Nom du fichier
            </label>
            <input
              autoFocus
              value={fileName}
              onChange={e => setFileName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') confirmSave(); if (e.key === 'Escape') setSaveDialog(false) }}
              style={{
                width: '100%', boxSizing: 'border-box', background: '#0a0a0a',
                border: '1px solid #30363d', borderRadius: 6, padding: '7px 10px',
                color: '#c9d1d9', fontSize: 12, fontFamily: 'monospace', outline: 'none',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
              <button onClick={() => setSaveDialog(false)} style={{
                background: 'transparent', border: '1px solid #30363d', borderRadius: 6,
                padding: '5px 12px', color: '#8b949e', fontSize: 12, cursor: 'pointer',
              }}>Annuler</button>
              <button onClick={confirmSave} style={{
                background: '#238636', border: '1px solid #2ea043', borderRadius: 6,
                padding: '5px 14px', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
              }}>Sauvegarder</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
