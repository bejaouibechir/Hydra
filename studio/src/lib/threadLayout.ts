/**
 * lib/threadLayout.ts — Disposition du schéma « Preview » de thread.yaml.
 *
 * De gauche à droite, une colonne par unité d'exécution (threadUnits) : un
 * workflow d'une étape séquentielle, ou toute une étape parallèle (blocs
 * empilés). Entre deux colonnes, un point de jonction ; c'est un losange quand
 * l'étape qui se termine a un délai (delay_after). Les boucles sont des flèches
 * de retour dessinées sous le schéma, avec « ×N » et un losange si elles ont
 * une pause.
 */
import { threadUnits, unitOf, isValidDelay, type ThreadLoop, type ThreadStage } from './thread'

export const NODE_W = 150
export const NODE_H = 40
const GAP_X = 96          // espace entre deux colonnes (jonction au milieu)
const GAP_Y = 18
const PAD = 24
const LOOP_STEP = 34      // décalage vertical entre deux boucles

export interface LNode { name: string; x: number; y: number; active: boolean; col: number }
export interface LJunction { x: number; y: number; delay: string | null }
export interface LEdge { d: string }
export interface LLoop { d: string; labelX: number; labelY: number; times: number; delay: string | null }
export interface Layout { width: number; height: number; nodes: LNode[]; junctions: LJunction[]; edges: LEdge[]; loops: LLoop[] }

const fmtDelay = (d: string | number | null | undefined): string | null => {
  if (d === undefined || d === null || d === '' || d === 0 || d === '0') return null
  if (!isValidDelay(d)) return null
  return typeof d === 'number' ? `${d}s` : (/^\s*\d+(\.\d+)?\s*$/.test(d) ? `${d.trim()}s` : d.trim())
}

export function layoutThread(stages: ThreadStage[], loops: ThreadLoop[] = []): Layout {
  const units = threadUnits(stages)
  const active = new Map(stages.flatMap(s => s.workflows.map(w => [w.name, w.active] as const)))
  const tallest = Math.max(1, ...units.map(u => u.names.length))
  const bodyH = tallest * NODE_H + (tallest - 1) * GAP_Y
  const cy = PAD + bodyH / 2
  const colX = (i: number) => PAD + i * (NODE_W + GAP_X)

  const nodes: LNode[] = []
  units.forEach((u, i) => {
    const h = u.names.length * NODE_H + (u.names.length - 1) * GAP_Y
    u.names.forEach((n, k) => nodes.push({
      name: n, col: i, active: active.get(n) ?? true,
      x: colX(i), y: cy - h / 2 + k * (NODE_H + GAP_Y),
    }))
  })
  const inCol = (i: number) => nodes.filter(n => n.col === i)

  const junctions: LJunction[] = []
  const edges: LEdge[] = []
  for (let i = 0; i < units.length - 1; i++) {
    const jx = colX(i) + NODE_W + GAP_X / 2
    const u = units[i]
    const delay = u.lastInStage ? fmtDelay(stages[u.stage].delay_after) : null
    junctions.push({ x: jx, y: cy, delay })
    for (const s of inCol(i)) {
      const sy = s.y + NODE_H / 2
      edges.push({ d: `M ${s.x + NODE_W} ${sy} H ${jx - 10} V ${cy} H ${jx}` })
    }
    for (const t of inCol(i + 1)) {
      const ty = t.y + NODE_H / 2
      edges.push({ d: `M ${jx} ${cy} H ${jx + 10} V ${ty} H ${t.x}` })
    }
  }

  const bottom = PAD + bodyH
  const outLoops: LLoop[] = []
  loops.forEach((lp, k) => {
    const a = unitOf(units, lp.to), b = unitOf(units, lp.from)
    if (a < 0 || b < 0 || a > b) return
    const y = bottom + 26 + k * LOOP_STEP
    const xb = colX(b) + NODE_W - 24, xa = colX(a) + 24
    const yb = Math.max(...inCol(b).map(n => n.y + NODE_H))
    const ya = Math.max(...inCol(a).map(n => n.y + NODE_H))
    outLoops.push({
      d: `M ${xb} ${yb} V ${y} H ${xa} V ${ya + 2}`,
      labelX: (xa + xb) / 2, labelY: y, times: lp.times, delay: fmtDelay(lp.delay),
    })
  })

  const width = PAD * 2 + Math.max(1, units.length) * NODE_W + Math.max(0, units.length - 1) * GAP_X
  const height = bottom + PAD + (outLoops.length ? 26 + outLoops.length * LOOP_STEP : 0)
  return { width, height, nodes, junctions, edges, loops: outLoops }
}
