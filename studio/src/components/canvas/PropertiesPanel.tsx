/**
 * PropertiesPanel — panneau droit du canvas.
 * Affiche et édite les propriétés du nœud sélectionné.
 */
import { useEffect, useRef } from 'react'
import { Node } from '@xyflow/react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { X } from 'lucide-react'
import { getNode } from '@/lib/nodeRegistry'

interface Props {
  node: Node<FlowNodeData> | null
  focusRename?: boolean
  onClose: () => void
  onChange: (id: string, data: Partial<FlowNodeData>) => void
}

export default function PropertiesPanel({ node, focusRename, onClose, onChange }: Props) {
  const nameRef = useRef<HTMLInputElement>(null)

  // Auto-focus sur le champ nom si rename demandé
  useEffect(() => {
    if (focusRename && nameRef.current) {
      nameRef.current.focus()
      nameRef.current.select()
    }
  }, [focusRename, node?.id])

  if (!node) return null

  const d    = node.data
  const def  = getNode(d.nodeType)

  return (
    <div
      className="w-64 shrink-0 flex flex-col overflow-y-auto"
      style={{
        background:  'var(--bg-card)',
        borderLeft:  '1px solid var(--bg-border)',
        position:    'relative',
        zIndex:      10,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b"
        style={{ borderColor: 'var(--bg-border)' }}>
        <div>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
            {def?.label ?? d.nodeType}
          </p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{def?.description}</p>
        </div>
        <button onClick={onClose} className="btn-ghost p-1 !gap-0">
          <X size={14} />
        </button>
      </div>

      <div className="p-3 space-y-3">
        {/* Step name */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Step name</label>
          <input
            ref={nameRef}
            className="input"
            value={d.stepName}
            onChange={e => onChange(node.id, { stepName: e.target.value, label: e.target.value })}
            placeholder="step_name"
          />
        </div>

        {/* Job path */}
        {(def?.category === 'source' || def?.category === 'destination' || def?.category === 'transformation' || !def) && (
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Job path</label>
            <input
              className="input font-mono text-xs"
              value={d.jobPath ?? ''}
              onChange={e => onChange(node.id, { jobPath: e.target.value })}
              placeholder="./jobs/my_job.yaml"
            />
          </div>
        )}

        {/* Action */}
        {def?.category === 'action' && (
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Node type</label>
            <p className="text-xs font-mono px-2 py-1 rounded"
              style={{ background: 'var(--bg-hover)', color: 'var(--text-primary)', fontWeight: 600 }}>
              {def?.label ?? d.nodeType}
            </p>
          </div>
        )}

        {/* on_failure */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>On failure</label>
          <select
            className="input"
            value={d.onFailure ?? 'fail'}
            onChange={e => onChange(node.id, { onFailure: e.target.value as FlowNodeData['onFailure'] })}
          >
            <option value="fail">fail (default)</option>
            <option value="skip">skip</option>
            <option value="continue">continue</option>
          </select>
        </div>

        {/* Node ID (readonly) */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Node ID</label>
          <p className="text-xs font-mono px-2 py-1 rounded"
            style={{ background: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
            {node.id}
          </p>
        </div>
      </div>
    </div>
  )
}

