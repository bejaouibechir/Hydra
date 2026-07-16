import { useEffect, useRef, useCallback } from 'react'
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

export default function TerminalPanel({ shell, initialCommand, onClose }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)

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

    return () => { ro.disconnect(); ws.close(); term.dispose() }
  }, [shell, initialCommand])

  useEffect(() => {
    const cleanup = connect()
    return () => { cleanup?.() }
  }, [connect])

  // Rendu IMBRIQUÉ : remplit le volet de l'onglet (pas d'overlay flottant).
  return (
    <div style={{ height: '100%', width: '100%', background: '#0d1117', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
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
      <div ref={containerRef} style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '6px' }} />
    </div>
  )
}
