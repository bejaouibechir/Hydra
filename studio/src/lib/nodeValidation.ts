/**
 * nodeValidation.ts — Validité d'un nœud (badge) + validité d'une connexion (arête).
 */
import type { FlowNodeData } from '@/lib/workflowSerializer'
import { getNode } from '@/lib/nodeRegistry'

const filled = (v?: unknown): boolean => {
  if (v == null) return false
  if (typeof v === 'string') return v.trim() !== ''
  if (Array.isArray(v)) return v.length > 0
  if (typeof v === 'object') return Object.keys(v as object).length > 0
  return true          // nombre, booléen → considéré renseigné
}

export function isNodeConfigured(data: FlowNodeData): boolean {
  const { jobPath, params } = data
  const nodeType = typeof data.nodeType === 'string' ? data.nodeType : ''
  const p = (params ?? {}) as Record<string, unknown>

  // Transformations
  if (nodeType.startsWith('transform_')) {
    if (filled(jobPath)) return true
    switch (nodeType) {
      case 'transform_filter':    return filled(p.expr)
      case 'transform_cast':      return filled(p.mapping)
      case 'transform_rename':    return filled(p.mapping)
      case 'transform_select':    return filled(p.columns)
      case 'transform_sort':      return filled(p.by)
      case 'transform_aggregate': return filled(p.by) && filled(p.agg)
      case 'transform_derive':    return filled(p.column) && filled(p.expr)
      default:                    return true
    }
  }

  // Actions génériques
  if (nodeType === 'action_webhook') return filled(p.url)
  if (nodeType === 'action_slack')   return filled(p.webhook_url)
  if (nodeType === 'action_email')   return filled(p.to) && filled(p.subject)

  // Actions shell — commande requise
  if (nodeType === 'action_powershell') return filled(p.command)
  if (nodeType === 'action_bash')       return filled(p.command)
  if (nodeType === 'action_python')     return filled(p.script) || filled(p.file_path)
  if (nodeType === 'action_ssh')        return filled(p.host) && filled(p.command)

  // Sources — un identifiant de données est requis (chemin, table, requête…)
  if (nodeType.startsWith('source_')) {
    if (filled(jobPath)) return true
    return filled(p.path) || filled(p.table) || filled(p.query) ||
           filled(p.collection) || filled(p.url) || filled(p.uri)
  }

  // Destinations — une cible est requise
  if (nodeType.startsWith('dest_')) {
    return filled(p.path) || filled(p.table) || filled(p.collection) || filled(p.uri)
  }

  // Job — une référence de job est requise
  if (nodeType === 'job') return filled(jobPath) || filled(p.job)

  // Control flow & autres → configurés par défaut
  return true
}

// ── Validation des connexions (arêtes) ───────────────────────────────────────

export interface ConnCheck { ok: boolean; reason?: string }

type MiniNode = { id: string; data?: { nodeType?: unknown } }
type MiniEdge = { source: string; target: string }

const typeOf = (n?: MiniNode): string =>
  (n && typeof n.data?.nodeType === 'string') ? (n.data!.nodeType as string) : ''

/** `to` est-il atteignable depuis `from` en suivant les arêtes ?
 *  (sert à détecter qu'ajouter une arête fermerait un cycle) */
function reaches(from: string, to: string, edges: MiniEdge[]): boolean {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    const arr = adj.get(e.source) ?? []
    arr.push(e.target)
    adj.set(e.source, arr)
  }
  const seen = new Set<string>()
  const stack = [from]
  while (stack.length) {
    const cur = stack.pop() as string
    if (cur === to) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const nxt of adj.get(cur) ?? []) stack.push(nxt)
  }
  return false
}

/**
 * Décide si une connexion peut être créée sur le canvas.
 * Applique : pas de boucle sur soi, pas de doublon, pas de conteneur en extrémité,
 * capacités maxInputs/maxOutputs du registre, et interdiction des cycles.
 */
export function validateConnection(
  conn: { source?: string | null; target?: string | null },
  nodes: MiniNode[],
  edges: MiniEdge[],
): ConnCheck {
  const { source, target } = conn
  if (!source || !target) return { ok: false, reason: 'Incomplete connection' }
  if (source === target)  return { ok: false, reason: 'A node cannot connect to itself' }

  const sNode = nodes.find(n => n.id === source)
  const tNode = nodes.find(n => n.id === target)
  if (!sNode || !tNode) return { ok: false, reason: 'Node not found' }

  const sType = typeOf(sNode)
  const tType = typeOf(tNode)
  if (sType === 'container' || tType === 'container')
    return { ok: false, reason: 'A container cannot be connected directly' }

  if (edges.some(e => e.source === source && e.target === target))
    return { ok: false, reason: 'This connection already exists' }

  const sDef = getNode(sType)
  const tDef = getNode(tType)

  if (sDef && sDef.maxOutputs === 0)
    return { ok: false, reason: `“${sDef.label}” cannot have an output` }
  if (tDef && tDef.maxInputs === 0)
    return { ok: false, reason: `“${tDef.label}” cannot have an input` }

  const outCount = edges.filter(e => e.source === source).length
  if (sDef && typeof sDef.maxOutputs === 'number' && sDef.maxOutputs > 0 && outCount >= sDef.maxOutputs)
    return { ok: false, reason: `“${sDef.label}” has reached its maximum number of outputs (${sDef.maxOutputs})` }

  const inCount = edges.filter(e => e.target === target).length
  if (tDef && typeof tDef.maxInputs === 'number' && tDef.maxInputs > 0 && inCount >= tDef.maxInputs)
    return { ok: false, reason: `“${tDef.label}” has reached its maximum number of inputs (${tDef.maxInputs})` }

  if (reaches(target, source, edges))
    return { ok: false, reason: 'This connection would create a cycle' }

  return { ok: true }
}
