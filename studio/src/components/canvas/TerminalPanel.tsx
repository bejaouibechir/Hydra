import { useEffect, useRef, useCallback, useState } from 'react'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import { WebLinksAddon } from 'xterm-addon-web-links'
import 'xterm/css/xterm.css'

interface TerminalPanelProps {
  shell: 'powershell' | 'bash'
  initialCommand?: string
  onClose: () => void
}

/** Construit l'URL WebSocket à partir de la même base que l'API HTTP
 *  (VITE_API_URL sinon le proxy Vite same-origin `/api`). Évite tout port
 *  codé en dur : le WS passe par le même chemin que les appels REST. */
function wsUrl(shell: string): string {
  const apiBase = ((import.meta.env.VITE_API_URL as string | undefined) ?? '/api').trim()
  let base: string
  if (/^https?:/i.test(apiBase)) {
    base = apiBase.replace(/^http/i, 'ws')
  } else {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const path = apiBase.startsWith('/') ? apiBase : `/${apiBase}`
    base = `${proto}//${window.location.host}${path}`
  }
  return `${base.replace(/\/+$/, '')}/terminal/ws?shell=${shell}`
}

/** Sérialise le buffer xterm en texte brut (lignes vides de fin retirées). */
function bufferText(term: Terminal): string {
  const buf = term.buffer.active
  const lines: string[] = []
  for (let i = 0; i < buf.length; i++) {
    const line = buf.getLine(i)
    if (line) lines.push(line.translateToString(true))
  }
  return lines.join('\n').replace(/\s+$/, '') + '\n'
}

function defaultLogName(shell: string): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `terminal_${shell}_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.log`
}

export default function TerminalPanel({ shell, initialCommand, onClose }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null)
  const [saveDialog, setSaveDialog] = useState(false)
  const [fileName, setFileName] = useState('')

  const connect = useCallback(() => {
    if (!containerRef.current) return

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Cascadia Code, Consolas, "Courier New", monospace',
      theme: {
        background:    '#0d1117',
        foreground:    '#c9d1d9',
        cursor:        '#58a6ff',
        black:         '#484f58',
        red:           '#ff7b72',
        green:         '#3fb950',
        yellow:        '#d29922',
        blue:          '#58a6ff',
        magenta:       '#bc8cff',
        cyan:          '#39c5cf',
        white:         '#b1bac4',
        brightBlack:   '#6e7681',
        brightRed:     '#ffa198',
        brightGreen:   '#56d364',
        brightYellow:  '#e3b341',
        brightBlue:    '#79c0ff',
        brightMagenta: '#d2a8ff',
        brightCyan:    '#56d4dd',
        brightWhite:   '#f0f6fc',
      },
    })
    termRef.current = term

    const fit   = new FitAddon()
    const links = new WebLinksAddon()
    term.loadAddon(fit)
    term.loadAddon(links)
    term.open(containerRef.current)
    setTimeout(() => { try { fit.fit(); term.focus() } catch { /* noop */ } }, 0)

    const ws = new WebSocket(wsUrl(shell))
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      term.writeln(`\x1b[32m● Connexion ${shell} \xe9tablie\x1b[0m`)
      if (initialCommand) {
        setTimeout(() => { ws.send(new TextEncoder().encode(initialCommand + '\r')) }, 400)
      }
    }

    ws.onmessage = (ev) => {
      const data = ev.data instanceof ArrayBuffer
        ? new Uint8Array(ev.data)
        : new TextEncoder().encode(String(ev.data))
      term.write(data)
    }

    ws.onerror = () => { term.writeln('\r\n\x1b[31m✗ Erreur WebSocket — backend injoignable\x1b[0m') }
    ws.onclose = () => { term.writeln('\r\n\x1b[33m● Session termin\xe9e\x1b[0m') }

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(data))
    })

    const ro = new ResizeObserver(() => { try { fit.fit() } catch { /* noop */ } })
    ro.observe(containerRef.current!)

    return () => { ro.disconnect(); ws.close(); term.dispose(); termRef.current = null }
  }, [shell, initialCommand])

  useEffect(() => {
    const cleanup = connect()
    return () => { cleanup?.() }
  }, [connect])

  // Fermer le menu contextuel au clic ailleurs / Échap
  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setCtxMenu(null) }
    window.addEventListener('click', close)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', onKey) }
  }, [ctxMenu])

  const doClear = () => { termRef.current?.clear(); setCtxMenu(null) }

  const doCopy = async () => {
    const term = termRef.current
    if (!term) return
    const sel = term.getSelection()
    const text = sel && sel.trim() ? sel : bufferText(term)
    try { await navigator.clipboard.writeText(text) } catch { /* clipboard indisponible */ }
    setCtxMenu(null)
  }

  const doSave = () => {
    setFileName(defaultLogName(shell))
    setSaveDialog(true)
    setCtxMenu(null)
  }

  const confirmSave = () => {
    const term = termRef.current
    if (!term) { setSaveDialog(false); return }
    const name = (fileName.trim() || defaultLogName(shell))
    const blob = new Blob([bufferText(term)], { type: 'text/plain;charset=utf-8' })
    const url  = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name.endsWith('.log') || name.includes('.') ? name : `${name}.log`
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

  // Rendu IMBRIQUÉ : remplit le volet de l'onglet (pas d'overlay flottant).
  return (
    <div style={{ height: '100%', width: '100%', background: '#0d1117', display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px', height: 28, flexShrink: 0,
        background: '#161b22', borderBottom: '1px solid #30363d',
      }}>
        {(['#ff5f57', '#febc2e', '#28c840'] as const).map((c, i) => (
          <div key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: c }} />
        ))}
        <span style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', fontFamily: 'monospace', letterSpacing: 1, marginLeft: 4 }}>TERMINAL</span>
        <span style={{
          fontSize: 10, padding: '1px 8px', borderRadius: 4,
          background: shell === 'powershell' ? '#2563eb22' : '#16a34a22',
          color:      shell === 'powershell' ? '#79c0ff'   : '#56d364',
          fontWeight: 700, letterSpacing: 0.5,
        }}>
          {shell === 'powershell' ? 'pwsh' : 'bash'}
        </span>
        <div style={{ flex: 1 }} />
        <button onClick={onClose} title="Close terminal" style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: '#8b949e', fontSize: 14, padding: '2px 6px', borderRadius: 4, lineHeight: 1,
        }}>{'✕'}</button>
      </div>
      <div
        ref={containerRef}
        style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '6px' }}
        onContextMenu={(e) => {
          e.preventDefault()
          const host = e.currentTarget.parentElement!.getBoundingClientRect()
          setCtxMenu({ x: e.clientX - host.left, y: e.clientY - host.top })
        }}
      />

      {/* Menu contextuel : Clear / Copy / Save */}
      {ctxMenu && (
        <div
          style={{
            position: 'absolute', left: Math.min(ctxMenu.x, 9999), top: ctxMenu.y, zIndex: 50,
            background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)', padding: '4px 0', minWidth: 150,
          }}
          onClick={(e) => e.stopPropagation()}
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
              Sauvegarder le log du terminal
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
                width: '100%', boxSizing: 'border-box', background: '#0d1117',
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
