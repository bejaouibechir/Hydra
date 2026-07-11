/**
 * NodeContextMenu — menu contextuel au clic droit sur un nœud.
 *
 * Actions :
 *   Open...        (↵)  → ouvre le panel propriétés
 *   Execute step   (Space) → run jusqu'à ce step
 *   Rename         (R)  → focus sur le champ stepName du panel
 *   Replace        (P)  → ouvre NodePalette en mode remplacement
 *   Deactivate/Activate (D) → toggle enabled
 *   ─────────────────────────
 *   Delete         (Del) → supprime le nœud
 */
import { useEffect, useRef } from 'react'
import { useReactFlow } from '@xyflow/react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { getNode } from '@/lib/nodeRegistry'
import {
  ExternalLink, Eye, Play, PencilLine, RefreshCw,
  PowerOff, Zap, Trash2, Pin, PinOff,
} from 'lucide-react'

export interface ContextMenuState {
  nodeId: string
  x: number
  y: number
}

interface Props {
  menu: ContextMenuState
  onClose: () => void
  onOpenPanel: (nodeId: string) => void
  onRename: (nodeId: string) => void
  onReplace: (nodeId: string) => void
  onRunStep: (nodeId: string) => void
  onViewData: (nodeId: string) => void
}

export default function NodeContextMenu({
  menu, onClose, onOpenPanel, onRename, onReplace, onRunStep, onViewData,
}: Props) {
  const rf  = useReactFlow()
  const ref = useRef<HTMLDivElement>(null)

  // Fermer au clic extérieur ou Escape
  useEffect(() => {
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      if (e instanceof MouseEvent && ref.current?.contains(e.target as Node)) return
      onClose()
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [onClose])

  const node = rf.getNode(menu.nodeId)
  if (!node) return null
  const d       = node.data as FlowNodeData
  const enabled = d.enabled !== false
  const pinned  = Boolean(d.pinned)
  const isDestination = getNode(d.nodeType as string)?.category === 'destination'

  const toggleEnabled = () => {
    rf.updateNodeData(menu.nodeId, { enabled: !enabled })
    onClose()
  }

  const togglePinned = () => {
    rf.updateNodeData(menu.nodeId, { pinned: !pinned })
    // React Flow draggable est contrôlé via updateNode
    rf.updateNode(menu.nodeId, { draggable: pinned }) // si était pinned → remettre draggable
    onClose()
  }

  const deleteNode = () => {
    rf.deleteElements({ nodes: [{ id: menu.nodeId }] })
    onClose()
  }

  const items: Array<{
    icon: React.ElementType
    label: string
    shortcut?: string
    action: () => void
    danger?: boolean
    dividerBefore?: boolean
  }> = [
    {
      icon: ExternalLink,
      label: 'Open…',
      shortcut: '↵',
      action: () => { onOpenPanel(menu.nodeId); onClose() },
    },
    ...(isDestination ? [{
      icon: Eye,
      label: 'View data',
      shortcut: 'V',
      action: () => { onViewData(menu.nodeId); onClose() },
    }] : []),
    {
      icon: Play,
      label: 'Execute step',
      shortcut: 'Space',
      action: () => { onRunStep(menu.nodeId); onClose() },
    },
    {
      icon: PencilLine,
      label: 'Rename',
      shortcut: 'R',
      action: () => { onRename(menu.nodeId); onClose() },
    },
    {
      icon: enabled ? PowerOff : Zap,
      label: enabled ? 'Deactivate' : 'Activate',
      shortcut: 'D',
      action: toggleEnabled,
    },
    {
      icon: Trash2,
      label: 'Delete',
      shortcut: 'Del',
      danger: true,
      dividerBefore: true,
      action: deleteNode,
    },
  ]

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        left:     menu.x,
        top:      menu.y,
        zIndex:   9999,
        minWidth: 200,
        borderRadius: 10,
        background: 'var(--bg-card)',
        border:   '1px solid var(--bg-border)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
        padding:  '4px 0',
        fontSize: 13,
      }}
    >
      {items.map((item) => (
        <div key={item.label}>
          {item.dividerBefore && (
            <div style={{ height: 1, background: 'var(--bg-border)', margin: '4px 0' }} />
          )}
          <button
            onClick={item.action}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '7px 14px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: item.danger ? 'var(--error)' : 'var(--text-primary)',
              textAlign: 'left',
              borderRadius: 0,
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.background = 'transparent'
            }}
          >
            <item.icon size={13} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.shortcut && (
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                {item.shortcut}
              </span>
            )}
          </button>
        </div>
      ))}
    </div>
  )
}
