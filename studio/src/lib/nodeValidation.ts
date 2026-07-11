/**
 * nodeValidation.ts — Détermine si un nœud est correctement configuré.
 */
import type { FlowNodeData } from '@/lib/workflowSerializer'

export function isNodeConfigured(data: FlowNodeData): boolean {
  const { jobPath, params } = data
  // nodeType peut manquer sur des données chargées du disk — jamais de crash
  const nodeType = typeof data.nodeType === 'string' ? data.nodeType : ''
  const p = (params ?? {}) as Record<string, unknown>
  // Les params venant d'un YAML disk peuvent être objet / tableau / nombre —
  // pas uniquement des strings saisies dans l'UI.
  const filled = (v?: unknown): boolean => {
    if (v == null) return false
    if (typeof v === 'string') return v.trim() !== ''
    if (Array.isArray(v)) return v.length > 0
    if (typeof v === 'object') return Object.keys(v as object).length > 0
    return true          // nombre, booléen → considéré renseigné
  }

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

  // Sources, destinations, control_flow, job → configurés par défaut
  return true
}

