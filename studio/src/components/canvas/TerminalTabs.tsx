/**
 * TerminalTabs — plusieurs terminaux dans le panneau du bas, comme dans VS Code.
 *
 *  - « + » ouvre un nouveau terminal (pwsh ou bash) ; × ferme un onglet ;
 *  - chaque onglet garde sa session tant qu'il est ouvert : passer d'un onglet à
 *    l'autre (ou sur LOGS / PARAMETERS / SECRETS) ne coupe pas le shell ;
 *  - fermer le dernier onglet ferme le terminal.
 */
import { useEffect, useRef, useState } from 'react'
import TerminalPanel from '@/components/canvas/TerminalPanel'

type Shell = 'powershell' | 'bash'

interface Tab { id: number; shell: Shell; n: number }

interface TerminalTabsProps {
  /** Shell du premier onglet, et des onglets ouverts par « + » sans choix. */
  defaultShell: Shell
  /** Demande d'ouverture d'un onglet venue d'ailleurs (boîte à outils) : un nouvel onglet par `seq`. */
  request?: { shell: Shell; seq: number } | null
  /** Le panneau est visible (onglet TERMINAL actif). */
  visible?: boolean
  onClose: () => void
}

const label = (sh: Shell) => (sh === 'powershell' ? 'pwsh' : 'bash')

export default function TerminalTabs({ defaultShell, request, visible = true, onClose }: TerminalTabsProps) {
  const nextId = useRef(1)
  const counters = useRef<Record<Shell, number>>({ powershell: 0, bash: 0 })
  const make = (shell: Shell): Tab => {
    counters.current[shell] += 1
    return { id: nextId.current++, shell, n: counters.current[shell] }
  }
  const [tabs, setTabs] = useState<Tab[]>(() => [make(request?.shell ?? defaultShell)])
  const [activeId, setActiveId] = useState<number>(tabs[0].id)
  const [menu, setMenu] = useState(false)
  const seenSeq = useRef<number | undefined>(request?.seq)

  const open = (shell: Shell) => {
    const t = make(shell)
    setTabs(ts => [...ts, t])
    setActiveId(t.id)
    setMenu(false)
  }

  // Ouverture demandée par la boîte à outils du canvas
  useEffect(() => {
    if (!request || request.seq === seenSeq.current) return
    seenSeq.current = request.seq
    open(request.shell)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.seq])

  const close = (id: number) => {
    setTabs(ts => {
      const i = ts.findIndex(t => t.id === id)
      const rest = ts.filter(t => t.id !== id)
      if (rest.length === 0) { setTimeout(onClose, 0); return ts }
      if (id === activeId) setActiveId(rest[Math.min(i, rest.length - 1)].id)
      return rest
    })
  }

  useEffect(() => {
    if (!menu) return
    const off = () => setMenu(false)
    window.addEventListener('click', off)
    return () => window.removeEventListener('click', off)
  }, [menu])

  const tabStyle = (on: boolean): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 6, height: 26, padding: '0 6px 0 10px',
    borderRight: '1px solid #30363d', cursor: 'pointer', fontSize: 11, fontFamily: 'monospace',
    color: on ? '#c9d1d9' : '#8b949e', background: on ? '#0d1117' : 'transparent',
    borderTop: on ? '2px solid #58a6ff' : '2px solid transparent',
  })
  const iconBtn: React.CSSProperties = {
    background: 'transparent', border: 'none', cursor: 'pointer', color: '#8b949e',
    fontSize: 13, lineHeight: 1, padding: '2px 6px', borderRadius: 4,
  }

  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column', background: '#0d1117' }}>
      <div data-testid="terminal-tabs" style={{
        display: 'flex', alignItems: 'stretch', height: 28, flexShrink: 0,
        background: '#161b22', borderBottom: '1px solid #30363d', position: 'relative',
      }}>
        {tabs.map(t => (
          <div key={t.id} style={tabStyle(t.id === activeId)} onClick={() => setActiveId(t.id)}
               title={`${label(t.shell)} ${t.n}`}>
            <span>{label(t.shell)} {t.n}</span>
            <button style={iconBtn} title="Close this terminal"
              onClick={(e) => { e.stopPropagation(); close(t.id) }}>×</button>
          </div>
        ))}
        <button style={{ ...iconBtn, padding: '0 10px', fontSize: 15 }} title="New terminal"
          onClick={(e) => { e.stopPropagation(); setMenu(m => !m) }}>+</button>
        {menu && (
          <div onClick={(e) => e.stopPropagation()} style={{
            position: 'absolute', top: 28, left: Math.min(tabs.length * 96, 600), zIndex: 50,
            background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: '4px 0',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)', minWidth: 160,
          }}>
            {(['powershell', 'bash'] as Shell[]).map(sh => (
              <button key={sh} onClick={() => open(sh)} style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '6px 14px',
                background: 'transparent', border: 'none', color: '#c9d1d9', fontSize: 12, cursor: 'pointer',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = '#21262d')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                New {label(sh)} terminal
              </button>
            ))}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <button style={iconBtn} title="Close all terminals" onClick={onClose}>✕</button>
      </div>
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {tabs.map(t => (
          <div key={t.id} style={{ position: 'absolute', inset: 0, display: t.id === activeId ? 'block' : 'none' }}>
            <TerminalPanel shell={t.shell} embedded active={visible && t.id === activeId}
              onClose={() => close(t.id)} />
          </div>
        ))}
      </div>
    </div>
  )
}
