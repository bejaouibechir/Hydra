/**
 * NodeContextMenu — menu contextuel au clic droit / bouton « … » d'un nœud.
 *
 * Actions :
 *   Open...        (↵)  → ouvre le panel propriétés
 *   Execute step   (Space) → run jusqu'à ce step
 *   Rename         (R)  → focus sur le champ stepName du panel
 *   Deactivate/Activate (D) → toggle enabled
 *   Add to container / Remove from container (submenu if several containers)
 *   ─────────────────────────
 *   Delete         (Del) → supprime le nœud
 */
import { useEffect, useRef, useState } from 'react'
import { useReactFlow } from '@xyflow/react'
import { isContainerNode, type FlowNodeData } from '@/lib/workflowSerializer'
import { isDescendant } from '@/lib/containers'
import { getNode } from '@/lib/nodeRegistry'
import {
  ExternalLink, Eye, Play, PencilLine,
  PowerOff, Zap, Trash2, Boxes, LogOut, ChevronRight,
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
  onAttachToContainer?: (nodeId: string, containerId: string) => void
  onDetachFromContainer?: (nodeId: string) => void
  isJobScene: boolean
}

type SubItem = { label: string; action: () => void }
type MenuItem = {
  icon: React.ElementType
  label: string
  shortcut?: string
  action?: () => void
  danger?: boolean
  dividerBefore?: boolean
  submenu?: SubItem[]
}

export default function NodeContextMenu({
  menu, onClose, onOpenPanel, onRename, onReplace, onRunStep, onViewData,
  onAttachToContainer, onDetachFromContainer, isJobScene,
}: Props) {
  const rf  = useReactFlow()
  const ref = useRef<HTMLDivElement>(null)
  const [subOpen, setSubOpen] = useState<string | null>(null)

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
  const isDestination = getNode(d.nodeType as string)?.category === 'destination'

  // Conteneurs disponibles (pour l'ajout) + parent courant (pour le retrait)
  const parentId = node.parentId
  // Conteneurs cibles : exclure soi-même, le parent actuel, et ses propres descendants
  const allNodes = rf.getNodes()
  const containers = allNodes
    .filter(isContainerNode)
    .filter(c => c.id !== menu.nodeId && c.id !== parentId && !isDescendant(allNodes as never, c.id, menu.nodeId))
    .map(c => ({ id: c.id, label: (c.data as FlowNodeData).label?.trim() || 'Sequence' }))

  const toggleEnabled = () => { rf.updateNodeData(menu.nodeId, { enabled: !enabled }); onClose() }
  const deleteNode = () => { rf.deleteElements({ nodes: [{ id: menu.nodeId }] }); onClose() }

  // ── Actions conteneur (nœuds ET conteneurs — imbrication supportée) ──────
  const containerItems: MenuItem[] = []
  {
    if (parentId && onDetachFromContainer) {
      containerItems.push({
        icon: LogOut,
        label: 'Remove from container',
        dividerBefore: true,
        action: () => { onDetachFromContainer(menu.nodeId); onClose() },
      })
    } else if (!parentId && onAttachToContainer && containers.length > 0) {
      if (containers.length === 1) {
        const c = containers[0]
        containerItems.push({
          icon: Boxes,
          label: 'Add to container',
          dividerBefore: true,
          action: () => { onAttachToContainer(menu.nodeId, c.id); onClose() },
        })
      } else {
        containerItems.push({
          icon: Boxes,
          label: 'Add to container',
          dividerBefore: true,
          submenu: containers.map(c => ({
            label: c.label,
            action: () => { onAttachToContainer(menu.nodeId, c.id); onClose() },
          })),
        })
      }
    }
  }

  const items: MenuItem[] = [
    { icon: ExternalLink, label: 'Open…', shortcut: '↵',
      action: () => { onOpenPanel(menu.nodeId); onClose() } },
    ...(isDestination ? [{ icon: Eye, label: 'View data', shortcut: 'V',
      action: () => { onViewData(menu.nodeId); onClose() } } as MenuItem] : []),
    ...(!isJobScene ? [{ icon: Play, label: 'Execute step', shortcut: 'Space',
      action: () => { onRunStep(menu.nodeId); onClose() } } as MenuItem] : []),
    { icon: PencilLine, label: 'Rename', shortcut: 'R',
      action: () => { onRename(menu.nodeId); onClose() } },
    { icon: enabled ? PowerOff : Zap, label: enabled ? 'Deactivate' : 'Activate', shortcut: 'D',
      action: toggleEnabled },
    ...containerItems,
    { icon: Trash2, label: 'Delete', shortcut: 'Del', danger: true, dividerBefore: true,
      action: deleteNode },
  ]

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed', left: menu.x, top: menu.y, zIndex: 9999,
        minWidth: 210, borderRadius: 10,
        background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.45)', padding: '4px 0', fontSize: 13,
      }}
    >
      {items.map((item) => (
        <div
          key={item.label}
          style={{ position: 'relative' }}
          onMouseEnter={() => setSubOpen(item.submenu ? item.label : null)}
        >
          {item.dividerBefore && (
            <div style={{ height: 1, background: 'var(--bg-border)', margin: '4px 0' }} />
          )}
          <button
            onClick={item.action}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%',
              padding: '7px 14px', background: 'transparent', border: 'none',
              cursor: 'pointer', color: item.danger ? 'var(--error)' : 'var(--text-primary)',
              textAlign: 'left', borderRadius: 0,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
          >
            <item.icon size={13} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.submenu ? (
              <ChevronRight size={13} style={{ color: 'var(--text-muted)' }} />
            ) : item.shortcut ? (
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                {item.shortcut}
              </span>
            ) : null}
          </button>

          {/* Sous-menu (choix du conteneur) */}
          {item.submenu && subOpen === item.label && (
            <div
              style={{
                position: 'absolute', left: '100%', top: 0, marginLeft: 2,
                minWidth: 180, maxHeight: 260, overflowY: 'auto',
                borderRadius: 10, background: 'var(--bg-card)',
                border: '1px solid var(--bg-border)', boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
                padding: '4px 0', zIndex: 10000,
              }}
            >
              {item.submenu.map(sub => (
                <button
                  key={sub.label}
                  onClick={sub.action}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                    padding: '7px 14px', background: 'transparent', border: 'none',
                    cursor: 'pointer', color: 'var(--text-primary)', textAlign: 'left',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <Boxes size={13} style={{ flexShrink: 0, color: 'var(--warning)' }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {sub.label}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
