import { memo } from 'react'
import { Handle, Position, NodeProps } from '@xyflow/react'
import { Zap } from 'lucide-react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import clsx from 'clsx'

export const ActionNode = memo(({ data, selected }: NodeProps) => {
  const d = data as FlowNodeData

  return (
    <div
      className={clsx('rounded-xl px-3 py-2.5 w-48 transition-all select-none')}
      style={{
        background: 'var(--bg-card)',
        border:     `1px solid ${selected ? 'var(--info)' : 'var(--bg-border)'}`,
        boxShadow:  selected ? '0 0 0 2px rgba(6,182,212,0.2)' : '0 2px 8px rgba(0,0,0,0.3)',
        minWidth:   192,
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: 'var(--info)', border: '2px solid var(--bg-card)', width: 10, height: 10 }} />

      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'rgba(6,182,212,0.15)' }}>
          <Zap size={13} style={{ color: 'var(--info)' }} />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
            {d.stepName || d.label}
          </p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {d.action ?? 'action'}
          </p>
        </div>
      </div>

      <Handle type="source" position={Position.Right}
        style={{ background: 'var(--info)', border: '2px solid var(--bg-card)', width: 10, height: 10 }} />
    </div>
  )
})
ActionNode.displayName = 'ActionNode'
