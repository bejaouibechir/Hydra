/**
 * ThreadPreview — schéma de workflows/thread.yaml (vue seule).
 * Blocs = workflows (grisés et pointillés s'ils sont inactifs, rouges si le
 * fichier manque) ; losange = délai entre deux étapes ; flèche de retour =
 * boucle (×N, losange si pause). Clic sur un bloc : ouvrir le workflow.
 */
import { layoutThread, NODE_H, NODE_W } from '@/lib/threadLayout'
import type { ThreadLoop, ThreadStage } from '@/lib/thread'

interface Props {
  stages: ThreadStage[]
  loops: ThreadLoop[]
  missing?: Set<string>
  onOpen?: (name: string) => void
}

const Diamond = ({ x, y, label, title }: { x: number; y: number; label: string; title: string }) => (
  <g>
    <title>{title}</title>
    <path d={`M ${x} ${y - 13} L ${x + 13} ${y} L ${x} ${y + 13} L ${x - 13} ${y} Z`}
      fill="var(--bg-card)" stroke="var(--warning)" strokeWidth={1.5} />
    <text x={x} y={y + 27} textAnchor="middle" fontSize={11} fill="var(--warning)" fontFamily="monospace">{label}</text>
  </g>
)

export default function ThreadPreview({ stages, loops, missing = new Set(), onOpen }: Props) {
  const l = layoutThread(stages, loops)
  if (l.nodes.length === 0) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)', padding: 12 }}>No workflow in the thread yet.</p>
  }
  return (
    <div data-testid="thread-preview" style={{ overflowX: 'auto', padding: '6px 0' }}>
      <svg viewBox={`0 0 ${l.width} ${l.height}`} role="img" aria-label="Execution order of the workflows"
        style={{ display: 'block', width: '100%', height: 'auto', maxWidth: l.width, minWidth: Math.min(l.width, 640) }}>
        <defs>
          <marker id="tp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-muted)" />
          </marker>
          <marker id="tp-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)" />
          </marker>
        </defs>

        {l.edges.map((e, i) => (
          <path key={i} d={e.d} fill="none" stroke="var(--text-muted)" strokeWidth={1.4} />
        ))}
        {/* flèches d'arrivée sur chaque bloc */}
        {l.nodes.filter(n => n.col > 0).map(n => (
          <path key={`in-${n.name}`} d={`M ${n.x - 12} ${n.y + NODE_H / 2} H ${n.x}`} stroke="var(--text-muted)"
            strokeWidth={1.4} markerEnd="url(#tp-arrow)" />
        ))}
        {l.junctions.map((j, i) => j.delay
          ? <Diamond key={i} x={j.x} y={j.y} label={j.delay} title={`Wait ${j.delay} before the next stage`} />
          : <circle key={i} cx={j.x} cy={j.y} r={3} fill="var(--text-muted)" />)}

        {l.loops.map((lp, i) => (
          <g key={`loop-${i}`}>
            <path d={lp.d} fill="none" stroke="var(--primary)" strokeWidth={1.6} strokeDasharray="5 4"
              markerEnd="url(#tp-loop)" />
            <rect x={lp.labelX - 26} y={lp.labelY - 10} width={52} height={20} rx={10}
              fill="var(--bg-card)" stroke="var(--primary)" />
            <text x={lp.labelX} y={lp.labelY + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="var(--primary)">
              ×{lp.times}
            </text>
            {lp.delay && <Diamond x={lp.labelX + 60} y={lp.labelY} label={lp.delay} title={`Pause ${lp.delay} before each repeat`} />}
          </g>
        ))}

        {l.nodes.map(n => {
          const miss = missing.has(n.name)
          return (
            <g key={n.name} data-testid={`preview-node-${n.name}`} onClick={() => onOpen?.(n.name)}
              style={{ cursor: onOpen ? 'pointer' : 'default' }}>
              <title>{miss ? `${n.name}: file missing` : n.active ? `Open ${n.name}` : `${n.name} (inactive, skipped)`}</title>
              <rect x={n.x} y={n.y} width={NODE_W} height={NODE_H} rx={10}
                fill="var(--bg-input)" stroke={miss ? 'var(--error)' : n.active ? 'var(--primary)' : 'var(--text-muted)'}
                strokeWidth={1.5} strokeDasharray={n.active ? undefined : '5 4'} opacity={n.active ? 1 : 0.55} />
              <text x={n.x + NODE_W / 2} y={n.y + NODE_H / 2 + 4} textAnchor="middle" fontSize={13}
                fontFamily="monospace" fill={n.active ? 'var(--text-primary)' : 'var(--text-muted)'}
                textDecoration={n.active ? undefined : 'line-through'}>
                {n.name.length > 18 ? n.name.slice(0, 17) + '…' : n.name}
              </text>
            </g>
          )
        })}
      </svg>
      <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '6px 0 0' }}>
        Left to right: stages in order; stacked blocks run in parallel; ◇ = wait before the next stage;
        dashed blue arrow = loop. Click a block to open the workflow.
      </p>
    </div>
  )
}
