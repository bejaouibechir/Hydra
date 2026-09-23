/**
 * HydraNode — nœud compact carré pour le canvas Hydra.
 *
 * Design :
 *  - Forme carrée 72×72px avec icône centrée
 *  - Tooltip (nom) au hover
 *  - NodeToolbar React Flow au hover : ▶ ⏻ ■ ···
 *  - enabled=false → opacité + filtre gris + bordure pointillée
 *  - Label (type · nom) affiché sous le carré
 */
import { memo, useCallback, useContext, useState, useRef, useEffect } from 'react'
import { SceneContext } from '@/lib/sceneContext'
import { Handle, Position, NodeProps, NodeToolbar, useReactFlow } from '@xyflow/react'
import {
  Play, PowerOff, Trash2, MoreHorizontal,
  Briefcase, Zap, Database, FileText, Globe,
  GitBranch, Shuffle, Layers, AlertCircle, Pin,
  ExternalLink, Clock,
} from 'lucide-react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { isNodeConfigured } from '@/lib/nodeValidation'

// ── Icône par nodeType / catégorie ────────────────────────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  job:             Briefcase,
  action_webhook:  Globe,
  action_log:      FileText,
  action_delay:    Clock,
  action_condition: GitBranch,
  action_email:    FileText,
  action_slack:    FileText,
  source_csv:      Database,
  source_json:     Database,
  source_parquet:  Database,
  source_mysql:    Database,
  source_postgres: Database,
  source_sqlserver: Database,
  source_mongodb:  Database,
  source_api:      Globe,
  transform:       Shuffle,
  workflow_split:  GitBranch,
  workflow_merge:  Layers,
  workflow_join:   Layers,
}

function nodeIcon(nodeType: string, category?: string): React.ElementType {
  return ICON_MAP[nodeType] ?? ICON_MAP[category ?? ''] ?? Briefcase
}

// ── Couleur d'accent par catégorie ────────────────────────────────────────────

const ACCENT: Record<string, string> = {
  source:         'var(--primary)',
  destination:    '#a78bfa',
  transformation: '#34d399',
  action:         'var(--info)',
  workflow:       'var(--warning)',
}

function nodeAccent(nodeType: string): string {
  for (const [key, color] of Object.entries(ACCENT)) {
    if (nodeType.startsWith(key) || nodeType === key) return color
  }
  return 'var(--primary)'
}

// ── Composant ─────────────────────────────────────────────────────────────────

export const HydraNode = memo(({ id, data, selected }: NodeProps) => {
  const d         = data as FlowNodeData
  const rf        = useReactFlow()
  const accent    = nodeAccent(d.nodeType)
  const Icon      = nodeIcon(d.nodeType)
  const enabled   = d.enabled !== false   // undefined → true

  // État d'exécution : blanc (initial) → pulsation (running) → vert/rouge
  const runStatus = (d as Record<string, unknown>).runStatus as 'running' | 'success' | 'failed' | undefined
  const RUN_COLORS = { running: 'var(--warning)', success: 'var(--success)', failed: 'var(--error)' } as const
  const runColor  = runStatus ? RUN_COLORS[runStatus] : undefined
  const [moreOpen, setMoreOpen] = useState(false)
  const scene = useContext(SceneContext)
  const moreRef   = useRef<HTMLDivElement>(null)

  // Ferme le dropdown si clic extérieur
  useEffect(() => {
    if (!moreOpen) return
    const handler = (e: MouseEvent) => {
      if (!moreRef.current?.contains(e.target as Node)) setMoreOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [moreOpen])

  // ── Actions toolbar ──────────────────────────────────────────────────────

  const handleRun = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    document.dispatchEvent(new CustomEvent('hydra:run-step', { detail: { nodeId: id } }))
  }, [id])

  const handleToggleEnabled = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    rf.updateNodeData(id, { enabled: !enabled })
  }, [id, enabled, rf])

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    rf.deleteElements({ nodes: [{ id }] })
  }, [id, rf])

  const handleMore = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    document.dispatchEvent(new CustomEvent('hydra:node-menu', { detail: { nodeId: id, x: rect.left, y: rect.bottom + 6 } }))
  }, [id])

  const handleOpen = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setMoreOpen(false)
    document.dispatchEvent(new CustomEvent('hydra:open-panel', { detail: { nodeId: id } }))
  }, [id])

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <>
      {/* Hover toolbar — React Flow NodeToolbar */}
      <NodeToolbar isVisible={selected || undefined} position={Position.Top}>
        <div
          className="flex items-center gap-0.5 px-1.5 py-1 rounded-lg"
          style={{
            background:  'var(--bg-card)',
            border:      '1px solid var(--bg-border)',
            boxShadow:   '0 4px 12px rgba(0,0,0,0.4)',
          }}
        >
          {scene !== 'jobs' && (
            <ToolbarBtn icon={Play} title="Execute step" color="var(--success)" onClick={handleRun} />
          )}
          <ToolbarBtn icon={PowerOff}  title={enabled ? 'Deactivate' : 'Activate'}
                      color={enabled ? 'var(--text-muted)' : 'var(--warning)'}
                      onClick={handleToggleEnabled} />
          <ToolbarBtn icon={Trash2}    title="Delete"       color="var(--error)"         onClick={handleDelete} />
          <div style={{ width: 1, height: 16, background: 'var(--bg-border)', margin: '0 2px' }} />

          {/* ··· avec mini dropdown */}
          <div ref={moreRef} style={{ position: 'relative' }}>
            <ToolbarBtn icon={MoreHorizontal} title="More" color="var(--text-secondary)" onClick={handleMore} />

          </div>
        </div>
      </NodeToolbar>

      {/* Nœud carré */}
      <div
        title={d.stepName}
        style={{
          width:      54,
          height:     54,
          borderRadius: 12,
          display:    'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-card)',
          border:     selected
            ? `2px solid ${accent}`
            : runColor
              ? `2px solid ${runColor}`
              : enabled
                ? `1px solid var(--bg-border)`
                : `1.5px dashed var(--bg-border)`,
          boxShadow:  selected
            ? `0 0 0 3px ${accent}40, 0 8px 24px rgba(0,0,0,0.45)`
            : runColor && runStatus !== 'running'
              ? `0 0 0 3px ${runColor}33, 0 4px 16px rgba(0,0,0,0.35)`
              : '0 4px 16px rgba(0,0,0,0.35), 0 1px 4px rgba(0,0,0,0.2)',
          animation:  runStatus === 'running' ? 'hydra-node-pulse 1.2s ease-in-out infinite' : undefined,
          opacity:    enabled ? 1 : 0.42,
          filter:     enabled ? 'none' : 'grayscale(0.7)',
          cursor:     d.pinned ? 'default' : 'grab',
          transition: 'opacity 0.2s, filter 0.2s, border-color 0.15s, box-shadow 0.15s',
          position:   'relative',
        }}
      >
        {/* Indicateur non configuré — rouge, disparaît quand tout est rempli */}
        {!isNodeConfigured(d) && (
          <div style={{ position: 'absolute', top: 4, right: 4 }}>
            <AlertCircle size={9} style={{ color: 'var(--error)' }} />
          </div>
        )}

        {/* Indicateur pin */}
        {d.pinned && (
          <div style={{ position: 'absolute', top: 3, left: 4 }}>
            <Pin size={9} style={{ color: accent, opacity: 0.8 }} />
          </div>
        )}

        {/* Icône principale */}
        <div
          style={{
            width: 28, height: 28,
            borderRadius: 7,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: `${accent}1a`,
          }}
        >
          <Icon size={14} style={{ color: accent }} />
        </div>

        {/* Handles */}
        <Handle
          type="target"
          position={Position.Left}
          style={{
            background: accent,
            border: '2px solid var(--bg-card)',
            width: 10, height: 10,
          }}
        />
        <Handle
          type="source"
          position={Position.Right}
          style={{
            background: accent,
            border: '2px solid var(--bg-card)',
            width: 10, height: 10,
          }}
        />
      </div>

      {/* Label sous le nœud */}
      <div style={{ textAlign: 'center', marginTop: 5, pointerEvents: 'none', maxWidth: 80, marginLeft: -13 }}>
        <p
          style={{
            fontSize: 9,
            fontWeight: 600,
            color: enabled ? 'var(--text-primary)' : 'var(--text-muted)',
            textDecoration: enabled ? 'none' : 'line-through',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {d.nodeType === 'job' ? d.label : d.stepName}
        </p>
        <p style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 1 }}>
          {d.nodeType === 'job' ? d.stepName : d.label}
        </p>
      </div>
    </>
  )
})

HydraNode.displayName = 'HydraNode'

// ── ToolbarBtn helper ─────────────────────────────────────────────────────────

function ToolbarBtn({
  icon: Icon, title, color, onClick,
}: {
  icon: React.ElementType
  title: string
  color: string
  onClick: (e: React.MouseEvent) => void
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      style={{
        padding: '3px 5px',
        borderRadius: 6,
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        color,
        display: 'flex',
        alignItems: 'center',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    >
      <Icon size={13} />
    </button>
  )
}
