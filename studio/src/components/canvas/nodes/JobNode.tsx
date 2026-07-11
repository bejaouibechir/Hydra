import { memo } from 'react'
import { Handle, Position, NodeProps } from '@xyflow/react'
import { Briefcase, AlertCircle } from 'lucide-react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import clsx from 'clsx'

export const JobNode = memo(({ data, selected }: NodeProps) => {
  const d = data as FlowNodeData
  const hasJob = Boolean(d.jobPath)

  return (
    <div
      className={clsx('rounded-xl px-3 py-2.5 w-48 transition-all select-none', selected && 'ring-2')}
      style={{
        background:  'var(--bg-card)',
        border:      `1px solid ${selected ? 'var(--primary)' : 'var(--bg-border)'}`,
        boxShadow:   selected ? '0 0 0 2px var(--primary-subtle)' : '0 2px 8px rgba(0,0,0,0.3)',
        minWidth:    192,
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: 'var(--primary)', border: '2px solid var(--bg-card)', width: 10, height: 10 }} />

      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'var(--primary-subtle)' }}>
          <Briefcase size={13} style={{ color: 'var(--primary)' }} />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
            {d.stepName || d.label}
          </p>
          <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
            {hasJob ? d.jobPath : <span style={{ color: 'var(--warning)' }} className="flex items-center gap-1">
              <AlertCircle size={10} /> no job set
            </span>}
          </p>
        </div>
      </div>

      {d.onFailure && d.onFailure !== 'fail' && (
        <div className="mt-1.5 text-xs px-1.5 py-0.5 rounded"
          style={{ background: 'rgba(245,158,11,0.12)', color: 'var(--warning)' }}>
          on_failure: {d.onFailure}
        </div>
      )}

      <Handle type="source" position={Position.Right}
        style={{ background: 'var(--primary)', border: '2px solid var(--bg-card)', width: 10, height: 10 }} />
    </div>
  )
})
JobNode.displayName = 'JobNode'
