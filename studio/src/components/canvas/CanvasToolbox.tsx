/**
 * CanvasToolbox — Boîte à outils verticale style Photoshop.
 * Placée entre la palette de nœuds et le canvas React Flow.
 *
 * Sections :
 *   ① Mode interaction  — Main (pan) | Flèche (sélection)
 *   ② Historique        — Undo | Redo
 *   ③ Vue              — Minimap toggle
 */
import type { ReactNode } from 'react'
import { Hand, MousePointer2, Undo2, Redo2, Map, Terminal } from 'lucide-react'

export type InteractionMode = 'pan' | 'select'

interface CanvasToolboxProps {
  interactionMode:  InteractionMode
  onModeChange:     (m: InteractionMode) => void
  canUndo:          boolean
  canRedo:          boolean
  onUndo:           () => void
  onRedo:           () => void
  minimapVisible:   boolean
  onToggleMinimap:  () => void
  logsVisible:      boolean
  onToggleLogs:     () => void
}

export default function CanvasToolbox({
  interactionMode, onModeChange,
  canUndo, canRedo, onUndo, onRedo,
  minimapVisible, onToggleMinimap,
  logsVisible, onToggleLogs,
}: CanvasToolboxProps) {
  return (
    <div style={{
      width: 44,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 4,
      padding: '10px 0',
      background: 'var(--bg-card)',
      borderRight: '1px solid var(--bg-border)',
      flexShrink: 0,
      userSelect: 'none',
    }}>

      {/* ── Mode interaction ── */}
      <Btn
        icon={<Hand size={15} />}
        title="Pan · Repositionner (H)"
        active={interactionMode === 'pan'}
        onClick={() => onModeChange('pan')}
      />
      <Btn
        icon={<MousePointer2 size={15} />}
        title="Select (V)"
        active={interactionMode === 'select'}
        onClick={() => onModeChange('select')}
      />

      <Sep />

      {/* ── Historique ── */}
      <Btn
        icon={<Undo2 size={15} />}
        title="Undo (Ctrl+Z)"
        active={false}
        disabled={!canUndo}
        onClick={onUndo}
      />
      <Btn
        icon={<Redo2 size={15} />}
        title="Redo (Ctrl+Y)"
        active={false}
        disabled={!canRedo}
        onClick={onRedo}
      />

      <Sep />

      {/* ── Vue ── */}
      <Btn
        icon={<Map size={15} />}
        title="Minimap"
        active={minimapVisible}
        onClick={onToggleMinimap}
      />
      <Btn
        icon={<Terminal size={15} />}
        title="Logs panel"
        active={logsVisible}
        onClick={onToggleLogs}
      />
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function Sep() {
  return (
    <div style={{
      width: 22, height: 1,
      background: 'var(--bg-border)',
      margin: '3px 0',
      flexShrink: 0,
    }} />
  )
}

function Btn({
  icon, title, active, disabled = false, onClick,
}: {
  icon: ReactNode; title: string
  active: boolean; disabled?: boolean; onClick: () => void
}) {
  const base: React.CSSProperties = {
    width: 32, height: 32,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: 8,
    background:   active ? 'var(--primary-subtle)' : 'transparent',
    border:       active ? '1px solid var(--primary)' : '1px solid transparent',
    color:        active  ? 'var(--primary)'
                : disabled ? 'var(--bg-border)'
                :            'var(--text-muted)',
    cursor:       disabled ? 'not-allowed' : 'pointer',
    transition:   'all 0.13s',
    flexShrink:   0,
  }

  return (
    <button
      title={title}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={base}
      onMouseEnter={e => {
        if (active || disabled) return
        const el = e.currentTarget as HTMLElement
        el.style.background = 'var(--bg-hover)'
        el.style.color      = 'var(--text-primary)'
      }}
      onMouseLeave={e => {
        if (active || disabled) return
        const el = e.currentTarget as HTMLElement
        el.style.background = 'transparent'
        el.style.color      = 'var(--text-muted)'
      }}
    >
      {icon}
    </button>
  )
}
