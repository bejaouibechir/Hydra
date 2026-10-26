/**
 * lib/threadLayout.ts — Disposition du schéma « Preview » de thread.yaml.
 *
 * De gauche à droite, une colonne par unité d'exécution (threadUnits) : un
 * workflow d'une étape séquentielle, ou toute une étape parallèle (blocs
 * empilés). Entre deux colonnes, un point de jonction ; c'est un losange quand
 * l'étape qui se termine a un délai (delay_after). Les boucles sont des flèches
 * de retour dessinées sous le schéma, avec « ×N » et un losange si elles ont
 * une pause. Les remplaçants d'un fallback sont des blocs pointillés placés
 * sous leur workflow, dans la même colonne, reliés par un trait pointillé
 * portant la condition. Un workflow avec delay_before porte une petite
 * horloge et la durée au-dessus de son coin gauche.
 */
import { threadUnits, unitOf, isValidDelay, type ThreadLoop, type ThreadStage } from './thread'

export const NODE_W = 150
export const NODE_H = 40
export const FB_H = 30    // bloc d'un remplaçant (fallback)
const FB_GAP = 30         // workflow → premier remplaçant (place de la condition)
const FB_GAP2 = 10        // entre deux remplaçants
const GAP_X = 96          // espace entre deux colonnes (jonction au milieu)
const GAP_Y = 18
const PAD = 24
const LOOP_STEP = 34      // décalage vertical entre deux boucles

export interface LNode {
  id: string; name: string; x: number; y: number; active: boolean; col: number
  h: number; fallbackOf?: string          // remplaçant : workflow du thread qu'il remplace
  wait?: string | null                    // delay_before (« 23s ») : horloge devant le bloc
}
export interface LFallback { d: string; labelX: number; labelY: number; label: string; title: string; of: string }
export interface LJunction { x: number; y: number; delay: string | null }
export interface LEdge { d: string }
export interface LLoop { d: string; labelX: number; labelY: number; times: number; delay: string | null }
export interface Layout {
  width: number; height: number; nodes: LNode[]; junctions: LJunction[]; edges: LEdge[]; loops: LLoop[]
  fallbacks: LFallback[]
}

const short = (t: string, n: number) => (t.length > n ? t.slice(0, n - 1) + '…' : t)

const fmtDelay = (d: string | number | null | undefined): string | null => {
  if (d === undefined || d === null || d === '' || d === 0 || d === '0') return null
  if (!isValidDelay(d)) return null
  return typeof d === 'number' ? `${d}s` : (/^\s*\d+(\.\d+)?\s*$/.test(d) ? `${d.trim()}s` : d.trim())
}

export function layoutThread(stages: ThreadStage[], loops: ThreadLoop[] = []): Layout {
  const units = threadUnits(stages)
  const byName = new Map(stages.flatMap(s => s.workflows.map(w => [w.name, w] as const)))
  const alts = (n: string) => byName.get(n)?.fallback?.use ?? []
  // hauteur d'un workflow avec ses remplaçants empilés dessous
  const groupH = (n: string) => {
    const k = alts(n).length
    return NODE_H + (k ? FB_GAP + k * FB_H + (k - 1) * FB_GAP2 : 0)
  }
  const colH = (u: { names: string[] }) => u.names.reduce((a, n) => a + groupH(n), 0) + (u.names.length - 1) * GAP_Y
  const bodyH = Math.max(NODE_H, ...units.map(colH))
  // ligne des flèches : au milieu des seuls workflows quand il n'y a aucun fallback
  const mainH = Math.max(1, ...units.map(u => u.names.length)) * NODE_H + (Math.max(1, ...units.map(u => u.names.length)) - 1) * GAP_Y
  const cy = PAD + mainH / 2
  const colX = (i: number) => PAD + i * (NODE_W + GAP_X)

  const nodes: LNode[] = []
  const fallbacks: LFallback[] = []
  units.forEach((u, i) => {
    const mainOnly = u.names.length * NODE_H + (u.names.length - 1) * GAP_Y
    let y = cy - mainOnly / 2
    u.names.forEach(n => {
      const x = colX(i)
      nodes.push({ id: n, name: n, col: i, active: byName.get(n)?.active ?? true, x, y, h: NODE_H,
        wait: fmtDelay(byName.get(n)?.delay_before) })
      const fb = byName.get(n)?.fallback
      let fy = y + NODE_H + FB_GAP
      alts(n).forEach((a, k) => {
        nodes.push({ id: `${n}>${a}`, name: a, col: i, active: byName.get(n)?.active ?? true,
          x: x + 12, y: fy, h: FB_H, fallbackOf: n })
        fy += FB_H + FB_GAP2
        if (k === 0) {
          const parts = [fb?.when ? `if ${fb.when}` : '', fb?.on_failure ? 'on failure' : ''].filter(Boolean)
          fallbacks.push({
            d: `M ${x + 24} ${y + NODE_H} V ${y + NODE_H + FB_GAP}`, of: n,
            labelX: x + 30, labelY: y + NODE_H + FB_GAP / 2 + 4,
            label: short(parts.join(' · ') || '?', 22),
            title: `${n} → ${alts(n).join(' → ')}: ${parts.join(', ') || 'no trigger'}`,
          })
        } else {
          fallbacks.push({
            d: `M ${x + 24} ${fy - FB_H - FB_GAP2 * 2} V ${fy - FB_H - FB_GAP2}`, of: n,
            labelX: x + 30, labelY: fy - FB_H - FB_GAP2, label: '', title: `then ${a}`,
          })
        }
      })
      y += groupH(n) + GAP_Y
    })
  })
  const mains = nodes.filter(n => !n.fallbackOf)
  const inCol = (i: number) => mains.filter(n => n.col === i)
  const allInCol = (i: number) => nodes.filter(n => n.col === i)

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

  const bottom = Math.max(PAD + bodyH, ...nodes.map(n => n.y + n.h))
  const outLoops: LLoop[] = []
  loops.forEach((lp, k) => {
    const a = unitOf(units, lp.to), b = unitOf(units, lp.from)
    if (a < 0 || b < 0 || a > b) return
    const y = bottom + 26 + k * LOOP_STEP
    const xb = colX(b) + NODE_W - 24, xa = colX(a) + 24
    const yb = Math.max(...allInCol(b).map(n => n.y + n.h))
    const ya = Math.max(...allInCol(a).map(n => n.y + n.h))
    outLoops.push({
      d: `M ${xb} ${yb} V ${y} H ${xa} V ${ya + 2}`,
      labelX: (xa + xb) / 2, labelY: y, times: lp.times, delay: fmtDelay(lp.delay),
    })
  })

  const width = PAD * 2 + Math.max(1, units.length) * NODE_W + Math.max(0, units.length - 1) * GAP_X
  const height = bottom + PAD + (outLoops.length ? 26 + outLoops.length * LOOP_STEP : 0)
  return { width, height, nodes, junctions, edges, loops: outLoops, fallbacks }
}
