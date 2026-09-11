/**
 * ContainerNode — conteneur de regroupement (Sequence, Error-scope, Retry-scope, …).
 *
 * Deux états :
 *  - Déplié  : montre les nœuds/jobs enfants, prend de la place, redimensionnable.
 *  - Replié  : petit rectangle listant les NOMS des enfants → gain de surface.
 *
 * Types « policy scope » (Error-scope, Retry-scope) : leur politique (on_failure,
 * retry) est recopiée sur les enfants à la sérialisation. Le conteneur lui-même
 * n'est jamais un step.
 *
 * Handles : présents UNIQUEMENT à l'état replié (ids c-tgt / c-src) pour les
 * edges « proxy » amont/aval.
 */
import { memo, useCallback } from 'react'
import { NodeProps, NodeResizer, Handle, Position, useReactFlow } from '@xyflow/react'
import { Boxes, ShieldAlert, RotateCcw, Repeat, Repeat1, Database, ChevronDown, ChevronRight } from 'lucide-react'
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { collapseContainer, expandContainer } from '@/lib/containers'

// ── Métadonnées par type de conteneur (extensible sans toucher au socle) ──────
type ContainerMeta = { label: string; icon: React.ElementType; accent: string }

const CONTAINER_META: Record<string, ContainerMeta> = {
  sequence:    { label: 'Sequence',    icon: Boxes,       accent: 'var(--warning)' },
  errorscope:  { label: 'Error Scope', icon: ShieldAlert, accent: 'var(--error)' },
  retryscope:  { label: 'Retry Scope', icon: RotateCcw,   accent: '#06b6d4' },
  // Prévus — non instanciés pour l'instant :
  for:         { label: 'For Loop',    icon: Repeat,      accent: '#f59e0b' },
  foreach:     { label: 'Foreach Loop',icon: Repeat1,     accent: '#f59e0b' },
  transaction: { label: 'Transaction', icon: Database,    accent: '#a78bfa' },
}

const MIN_W = 220
const MIN_H = 160
const MAX_LIST = 8
const ON_FAILURE_OPTS = ['skip', 'continue', 'fail'] as const

export const ContainerNode = memo(({ id, data, selected }: NodeProps) => {
  const d = data as FlowNodeData
  const ctype = (d.containerType as string) ?? 'sequence'
  const meta  = CONTAINER_META[ctype] ?? CONTAINER_META.sequence
  const Icon  = meta.icon
  const title = d.label?.trim() || meta.label
  const collapsed = d.collapsed === true
  const childCount = (d.childCount as number) ?? 0
  const childLabels = (d.childLabels as string[]) ?? []
  const shown = childLabels.slice(0, MAX_LIST)
  const extra = childLabels.length - shown.length

  const isErrorScope = ctype === 'errorscope'
  const isRetryScope = ctype === 'retryscope'
  const onFailure = (d.onFailure as string) ?? 'skip'
  const retry = (d.retry as { max?: number; delay?: number }) ?? { max: 3, delay: 5 }

  const { getNodes, getEdges, setNodes, setEdges, updateNodeData } = useReactFlow()

  const toggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    const ns = getNodes()
    const es = getEdges()
    const res = collapsed
      ? expandContainer(ns as never, es, id)
      : collapseContainer(ns as never, es, id)
    setNodes(res.nodes as never)
    setEdges(res.edges)
  }, [collapsed, id, getNodes, getEdges, setNodes, setEdges])

  const setRetry = useCallback((patch: { max?: number; delay?: number }) => {
    updateNodeData(id, { retry: { max: retry.max ?? 3, delay: retry.delay ?? 5, ...patch } })
  }, [id, retry.max, retry.delay, updateNodeData])

  const handleStyle = {
    width: 8, height: 8, borderRadius: '50%',
    background: meta.accent, border: '2px solid var(--bg-card)',
  } as const

  const numInputStyle = {
    width: 42, fontSize: 11, fontFamily: 'monospace', fontWeight: 700,
    color: meta.accent, background: 'var(--bg-card)',
    border: `1px solid ${meta.accent}55`, borderRadius: 6, padding: '1px 4px',
  } as const

  return (
    <>
      <NodeResizer
        isVisible={!collapsed}
        minWidth={MIN_W}
        minHeight={MIN_H}
        lineStyle={{ borderColor: meta.accent }}
        handleStyle={{ width: 8, height: 8, borderRadius: 2, background: meta.accent }}
      />

      {/* Handles pour les edges proxy — uniquement quand replié */}
      {collapsed && (
        <>
          <Handle id="c-tgt" type="target" position={Position.Left}  isConnectable={false} style={handleStyle} />
          <Handle id="c-src" type="source" position={Position.Right} isConnectable={false} style={handleStyle} />
        </>
      )}

      <div
        style={{
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
          borderRadius: 12,
          border: `1.5px ${selected ? 'solid' : 'dashed'} ${meta.accent}`,
          background: collapsed
            ? `color-mix(in srgb, ${meta.accent} 12%, var(--bg-card))`
            : 'color-mix(in srgb, var(--bg-card) 78%, transparent)',
          backdropFilter: 'blur(1px)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Barre de titre (poignée de déplacement du groupe) */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 9px',
            borderBottom: collapsed ? `1px solid ${meta.accent}55` : `1px solid ${meta.accent}`,
            background: `color-mix(in srgb, ${meta.accent} 14%, transparent)`,
            color: 'var(--text-primary)',
            fontSize: 12, fontWeight: 700,
            userSelect: 'none',
          }}
        >
          <button
            onClick={toggle}
            title={collapsed ? 'Expand' : 'Collapse'}
            className="nodrag"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 18, height: 18, flexShrink: 0,
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: meta.accent, padding: 0,
            }}
          >
            {collapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}
          </button>

          <Icon size={14} style={{ color: meta.accent, flexShrink: 0 }} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {title}
          </span>

          {collapsed ? (
            <span
              style={{
                marginLeft: 'auto', flexShrink: 0,
                fontSize: 10, fontWeight: 700,
                color: meta.accent,
                background: `color-mix(in srgb, ${meta.accent} 22%, transparent)`,
                borderRadius: 10, padding: '0px 7px',
                fontFamily: 'monospace',
              }}
              title={`${childCount} grouped item(s)`}
            >
              {childCount}
            </span>
          ) : (
            <span
              style={{
                marginLeft: 'auto', flexShrink: 0,
                fontSize: 9, fontWeight: 700, letterSpacing: 0.6,
                textTransform: 'uppercase',
                color: meta.accent, opacity: 0.8,
                fontFamily: 'monospace',
              }}
            >
              {meta.label}
            </span>
          )}
        </div>

        {/* Config Error-scope (déplié) */}
        {isErrorScope && !collapsed && (
          <div
            className="nodrag"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 10px', fontSize: 11,
              color: 'var(--text-secondary)',
              borderBottom: `1px solid ${meta.accent}33`,
            }}
          >
            <span>On child failure:</span>
            <select
              value={onFailure}
              onChange={e => { e.stopPropagation(); updateNodeData(id, { onFailure: e.target.value }) }}
              onClick={e => e.stopPropagation()}
              style={{
                fontSize: 11, fontFamily: 'monospace', fontWeight: 700,
                color: meta.accent, background: 'var(--bg-card)',
                border: `1px solid ${meta.accent}55`, borderRadius: 6,
                padding: '1px 4px', cursor: 'pointer',
              }}
            >
              {ON_FAILURE_OPTS.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        )}

        {/* Config Retry-scope (déplié) */}
        {isRetryScope && !collapsed && (
          <div
            className="nodrag"
            style={{
              display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
              padding: '5px 10px', fontSize: 11,
              color: 'var(--text-secondary)',
              borderBottom: `1px solid ${meta.accent}33`,
            }}
          >
            <span>Retries</span>
            <input
              type="number" min={0} value={retry.max ?? 3}
              onChange={e => { e.stopPropagation(); setRetry({ max: Math.max(0, Number(e.target.value) || 0) }) }}
              onClick={e => e.stopPropagation()}
              style={numInputStyle}
            />
            <span>×, delay</span>
            <input
              type="number" min={0} value={retry.delay ?? 5}
              onChange={e => { e.stopPropagation(); setRetry({ delay: Math.max(0, Number(e.target.value) || 0) }) }}
              onClick={e => e.stopPropagation()}
              style={numInputStyle}
            />
            <span>s</span>
          </div>
        )}

        {/* Corps */}
        {collapsed ? (
          <div style={{ padding: '3px 8px 5px', display: 'flex', flexDirection: 'column', gap: 1, overflow: 'hidden' }}>
            {isErrorScope && (
              <div style={{ fontSize: 9.5, fontWeight: 700, color: meta.accent, fontFamily: 'monospace', marginBottom: 1 }}>
                on_failure: {onFailure}
              </div>
            )}
            {isRetryScope && (
              <div style={{ fontSize: 9.5, fontWeight: 700, color: meta.accent, fontFamily: 'monospace', marginBottom: 1 }}>
                retry: {retry.max ?? 3}× / {retry.delay ?? 5}s
              </div>
            )}
            {childLabels.length === 0 && (
              <div style={{ fontSize: 10, fontStyle: 'italic', color: 'var(--text-muted)' }}>empty</div>
            )}
            {shown.map((name, i) => (
              <div
                key={i}
                title={name}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  fontSize: 10.5, lineHeight: '15px', color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}
              >
                <span style={{ width: 4, height: 4, borderRadius: '50%', background: meta.accent, flexShrink: 0 }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
              </div>
            ))}
            {extra > 0 && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', paddingLeft: 9 }}>+{extra} …</div>
            )}
          </div>
        ) : (
          <div style={{ flex: 1 }} />
        )}
      </div>
    </>
  )
})

ContainerNode.displayName = 'ContainerNode'
