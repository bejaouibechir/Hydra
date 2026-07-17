/**
 * containers.ts — Regroupement visuel des conteneurs (Sequence / Error / Retry …),
 * avec IMBRICATION à profondeur arbitraire (un conteneur dans un conteneur).
 *
 * Modèle DÉCLARATIF : l'état visible dérive uniquement des drapeaux `collapsed`.
 * `syncContainers(nodes, edges)` recalcule, pour toute la scène :
 *   - `hidden` de chaque nœud = il a (au moins) un ancêtre replié ;
 *   - la taille de chaque conteneur (replié = petit rectangle + liste, sinon prev) ;
 *   - les edges « proxy » : toute arête franchissant une frontière de repli est
 *     rerouteée vers le conteneur replié VISIBLE le plus externe de chaque extrémité.
 *
 * Toutes les opérations (collapse/expand/attach/detach/load) ne font que modifier
 * la structure (drapeau `collapsed` ou `parentId`) puis appellent `syncContainers`.
 *
 * La sérialisation YAML n'est pas concernée : les conteneurs restent exclus, et
 * l'héritage de politique (on_failure/retry) se fait par parent DIRECT.
 */
import type { Node, Edge } from '@xyflow/react'
import { MarkerType } from '@xyflow/react'
import { isContainerNode, isProxyEdge, PROXY_EDGE_PREFIX, type FlowNodeData } from './workflowSerializer'

export const COLLAPSED_W = 210
const COLLAPSED_HEADER_H = 30
const COLLAPSED_ROW_H = 16
const COLLAPSED_MAX_ROWS = 8
const DEFAULT_EXPANDED_W = 320
const DEFAULT_EXPANDED_H = 220
const CHILD_MIN_Y = 30

type N = Node<FlowNodeData>
type Res = { nodes: N[]; edges: Edge[] }

const isCollapsed = (n?: N): boolean => (n?.data as { collapsed?: boolean } | undefined)?.collapsed === true

/** Enfants DIRECTS d'un conteneur. */
export function childIdsOf(nodes: Node[], containerId: string): Set<string> {
  return new Set(nodes.filter(n => n.parentId === containerId).map(n => n.id))
}

function labelOf(n: N): string {
  const d = n.data
  return (d?.label?.trim() || (d?.stepName as string) || n.id)
}

function collapsedHeight(count: number): number {
  const rows  = Math.min(count, COLLAPSED_MAX_ROWS)
  const extra = count > COLLAPSED_MAX_ROWS ? 1 : 0
  return COLLAPSED_HEADER_H + Math.max(rows + extra, 1) * COLLAPSED_ROW_H + 8
}

function dimOf(n: N | undefined, key: 'width' | 'height', fallback: number): number {
  const top = (n as { width?: number; height?: number } | undefined)?.[key]
  if (typeof top === 'number') return top
  const st = n?.style?.[key]
  return typeof st === 'number' ? st : fallback
}

/** Position absolue (remonte toute la chaîne parentId). */
function absolutePos(byId: Map<string, N>, node: N): { x: number; y: number } {
  let x = node.position.x, y = node.position.y
  let cur = node.parentId ? byId.get(node.parentId) : undefined
  const seen = new Set<string>([node.id])
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    x += cur.position.x; y += cur.position.y
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  return { x, y }
}

/** Ancêtre replié le plus EXTERNE d'un nœud (ou null). */
function outermostCollapsedAncestor(byId: Map<string, N>, node: N): string | null {
  let result: string | null = null
  const seen = new Set<string>([node.id])
  let cur = node.parentId ? byId.get(node.parentId) : undefined
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    if (isCollapsed(cur)) result = cur.id       // garde le plus haut trouvé
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  return result
}

/** Profondeur d'imbrication (pour l'ordre parent-avant-enfant). */
function depthOf(byId: Map<string, N>, node: N): number {
  let d = 0
  const seen = new Set<string>([node.id])
  let cur = node.parentId ? byId.get(node.parentId) : undefined
  while (cur && !seen.has(cur.id)) { seen.add(cur.id); d++; cur = cur.parentId ? byId.get(cur.parentId) : undefined }
  return d
}

/** Parent-avant-enfant, profondeur croissante (tri stable). */
function parentsFirst(ns: N[]): N[] {
  const byId = new Map(ns.map(n => [n.id, n]))
  return ns
    .map((n, i) => ({ n, i, d: depthOf(byId, n) }))
    .sort((a, b) => a.d - b.d || a.i - b.i)
    .map(x => x.n)
}

/** Recalcule masquages + tailles + proxies à partir des drapeaux `collapsed`. */
export function syncContainers(nodes: N[], edges: Edge[]): Res {
  const byId = new Map(nodes.map(n => [n.id, n]))

  const rep = new Map<string, string>()
  const hidden = new Map<string, boolean>()
  for (const n of nodes) {
    const oca = outermostCollapsedAncestor(byId, n)
    rep.set(n.id, oca ?? n.id)
    hidden.set(n.id, oca !== null)
  }

  const directChildren = new Map<string, N[]>()
  for (const n of nodes) {
    if (n.parentId) {
      const arr = directChildren.get(n.parentId) ?? []
      arr.push(n); directChildren.set(n.parentId, arr)
    }
  }

  const outNodes = nodes.map(n => {
    const isHidden = hidden.get(n.id) === true
    let m: N = { ...n, hidden: isHidden }
    // extent : 'parent' seulement si visible ET enfant (évite le clamp d'un enfant masqué)
    if (n.parentId) (m as { extent?: unknown }).extent = isHidden ? undefined : 'parent'

    if (isContainerNode(n)) {
      if (isCollapsed(n)) {
        const kids = directChildren.get(n.id) ?? []
        const labels = kids.map(labelOf)
        const pd = (m.data ?? {}) as { prevH?: number; prevW?: number }
        const prevW = pd.prevW ?? dimOf(n, 'width', DEFAULT_EXPANDED_W)
        const prevH = pd.prevH ?? dimOf(n, 'height', DEFAULT_EXPANDED_H)
        const ch = collapsedHeight(kids.length)
        m = { ...m, width: COLLAPSED_W, height: ch,
              data: { ...m.data, collapsed: true, prevW, prevH, childCount: kids.length, childLabels: labels },
              style: { ...(m.style ?? {}), width: COLLAPSED_W, height: ch } }
      } else {
        const pd = (m.data ?? {}) as { prevH?: number; prevW?: number; childCount?: number; childLabels?: string[] }
        const prevW = pd.prevW ?? dimOf(n, 'width', DEFAULT_EXPANDED_W)
        const prevH = pd.prevH ?? dimOf(n, 'height', DEFAULT_EXPANDED_H)
        const { prevH: _h, prevW: _w, childCount: _c, childLabels: _l, ...restData } =
          m.data as FlowNodeData & { prevH?: number; prevW?: number; childCount?: number; childLabels?: string[] }
        m = { ...m, width: prevW, height: prevH,
              data: { ...restData, collapsed: false },
              style: { ...(m.style ?? {}), width: prevW, height: prevH } }
      }
    }
    return m
  })

  const seen = new Set<string>()
  const proxies: Edge[] = []
  const outEdges: Edge[] = []
  for (const e of edges) {
    if (isProxyEdge(e)) continue
    const repS = rep.get(e.source) ?? e.source
    const repT = rep.get(e.target) ?? e.target
    if (repS === repT) {
      outEdges.push(e.hidden ? e : { ...e, hidden: true })          // interne à un même repli
    } else if (repS !== e.source || repT !== e.target) {
      outEdges.push(e.hidden ? e : { ...e, hidden: true })          // franchit une frontière
      const key = `${repS}__${repT}`
      if (!seen.has(key)) {
        seen.add(key)
        proxies.push({
          id: `${PROXY_EDGE_PREFIX}${key}`,
          source: repS, target: repT,
          sourceHandle: isContainerNode(byId.get(repS)) ? 'c-src' : undefined,
          targetHandle: isContainerNode(byId.get(repT)) ? 'c-tgt' : undefined,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
          style: { strokeDasharray: '5 3' },
        })
      }
    } else {
      outEdges.push(e.hidden ? { ...e, hidden: false } : e)         // pleinement visible
    }
  }

  return { nodes: parentsFirst(outNodes), edges: [...outEdges, ...proxies] }
}

// ── API stable (mêmes signatures qu'avant) ────────────────────────────────────

export function collapseContainer(nodes: N[], edges: Edge[], containerId: string): Res {
  return syncContainers(nodes.map(n => n.id === containerId ? { ...n, data: { ...n.data, collapsed: true } } : n), edges)
}

export function expandContainer(nodes: N[], edges: Edge[], containerId: string): Res {
  return syncContainers(nodes.map(n => n.id === containerId ? { ...n, data: { ...n.data, collapsed: false } } : n), edges)
}

export function applyCollapsedState(nodes: N[], edges: Edge[]): Res {
  return syncContainers(nodes, edges)
}

/** Rattache un nœud (ou un conteneur) à un conteneur. Empêche les cycles. */
export function attachNodeToContainer(nodes: N[], edges: Edge[], nodeId: string, containerId: string): Res {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const node = byId.get(nodeId), container = byId.get(containerId)
  if (!node || !container || nodeId === containerId) return { nodes, edges }
  // Cycle : containerId ne doit pas être un descendant de nodeId
  let cur: N | undefined = container
  const seen = new Set<string>()
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    if (cur.parentId === nodeId) return { nodes, edges }
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  const abs  = absolutePos(byId, node)
  const cAbs = absolutePos(byId, container)
  const rel  = { x: abs.x - cAbs.x, y: Math.max(CHILD_MIN_Y, abs.y - cAbs.y) }
  const ns = nodes.map(n => n.id === nodeId
    ? { ...n, parentId: containerId, extent: 'parent' as const, position: rel } : n)
  return syncContainers(ns, edges)
}

/** Détache un nœud de son conteneur (position → absolue). */
export function detachNode(nodes: N[], edges: Edge[], nodeId: string): Res {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const node = byId.get(nodeId)
  if (!node?.parentId) return { nodes, edges }
  const abs = absolutePos(byId, node)
  const ns = nodes.map(n => {
    if (n.id !== nodeId) return n
    const { parentId: _p, extent: _e, ...rest } = n as N & { extent?: unknown }
    return { ...(rest as N), position: { x: abs.x, y: abs.y } }
  })
  return syncContainers(ns, edges)
}

/** Vrai si `nodeId` est un descendant de `ancestorId` (chaîne parentId). */
export function isDescendant(nodes: N[], nodeId: string, ancestorId: string): boolean {
  const byId = new Map(nodes.map(n => [n.id, n]))
  let cur = byId.get(nodeId)
  const seen = new Set<string>()
  while (cur?.parentId && !seen.has(cur.id)) {
    seen.add(cur.id)
    if (cur.parentId === ancestorId) return true
    cur = byId.get(cur.parentId)
  }
  return false
}
