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

const WS_BASE = 'ws://localhost:8000/api/terminal/ws'

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
    fit.fit()

    const ws = new WebSocket(`${WS_BASE}?shell=${shell}`)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      term.writeln(`\x1b[32m\u25cf Connexion ${shell} \xe9tablie\x1b[0m`)
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

    ws.onerror  = () => { term.writeln('\r\n\x1b[31m\u2717 Erreur WebSocket\x1b[0m') }
    ws.onclose  = () => { term.writeln('\r\n\x1b[33m\u25cf Session termin\xe9e\x1b[0m') }

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(data))
    })

    const ro = new ResizeObserver(() => { try { fit.fit() } catch {} })
    ro.observe(containerRef.current!)

    return () => { ro.disconnect(); ws.close(); term.dispose() }
  }, [shell, initialCommand])

  useEffect(() => {
    const cleanup = connect()
    return () => { cleanup?.() }
  }, [connect])

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 'min(960px, 93vw)', height: 'min(580px, 82vh)',
          background: '#0d1117', borderRadius: 10,
          border: '1px solid #30363d',
          boxShadow: '0 24px 64px rgba(0,0,0,0.75)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Title bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '0 14px', height: 36, flexShrink: 0,
          background: '#161b22', borderBottom: '1px solid #30363d',
        }}>
          {(['#ff5f57','#febc2e','#28c840'] as const).map((c, i) => (
            <div key={i} style={{ width: 12, height: 12, borderRadius: '50%', background: c }} />
          ))}
          <span style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', fontFamily: 'monospace', letterSpacing: 1, marginLeft: 4 }}>
            TERMINAL
          </span>
          <span style={{
            fontSize: 10, padding: '1px 8px', borderRadius: 4, marginLeft: 2,
            background: shell === 'powershell' ? '#2563eb22' : '#16a34a22',
            color:      shell === 'powershell' ? '#79c0ff'   : '#56d364',
            fontWeight: 700, letterSpacing: 0.5,
          }}>
            {shell === 'powershell' ? 'pwsh' : 'bash'}
          </span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 10, color: '#484f58', fontFamily: 'monospace' }}>Esc pour fermer</span>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: '#8b949e', fontSize: 15, padding: '2px 6px', borderRadius: 4, marginLeft: 8,
          }}>\u2715</button>
        </div>

        {/* xterm container */}
        <div ref={containerRef} style={{ flex: 1, overflow: 'hidden', padding: '6px 2px' }} />
      </div>
    </div>
  )
}
