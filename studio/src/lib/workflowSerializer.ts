/**
 * workflowSerializer.ts — Conversion bidirectionnelle
 * React Flow (nodes + edges) ↔ Hydra workflow.yaml structure
 */
import type { Node, Edge } from '@xyflow/react'
import { load as yamlLoad, dump as yamlDump } from 'js-yaml'
import { topologicalSort, edgesToDAGNodes, validateDAG, computeLevels } from './dag'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface WorkflowStep {
  name: string
  type: 'job' | 'action'
  job?: string
  action?: string
  params?: Record<string, unknown>
  depends_on?: string[]
  on_failure?: 'fail' | 'skip' | 'continue'
  enabled?: boolean   // false → step ignoré à l'exécution
  retry?: RetryPolicy  // re-tentatives (via Retry-scope)
  when?: string        // garde conditionnelle : step exécuté seulement si l'expression est vraie
}

export interface RetryPolicy {
  max: number                          // re-tentatives après le 1er échec
  delay?: number                       // secondes entre tentatives
  backoff?: 'fixed' | 'exponential'
}

export interface WorkflowYAML {
  version: '1.0'
  workflow: {
    name: string
    trigger: {
      type: 'manual' | 'schedule' | 'webhook'
      cron?: string
    }
    steps: WorkflowStep[]
  }
}

export interface FlowNodeData extends Record<string, unknown> {
  label: string
  nodeType: string        // HydraNodeDef.type
  stepName: string        // nom du step dans workflow.yaml
  jobPath?: string        // chemin vers le job (type=job)
  action?: string         // action (type=action)
  params?: Record<string, unknown>
  onFailure?: WorkflowStep['on_failure']
  enabled?: boolean       // false → nœud désactivé (grisé + ignoré à l'exécution)
  pinned?: boolean        // true → nœud immobilisé sur le canvas (draggable: false)
  when?: string           // garde conditionnelle 'when' (routage via nœud Condition)
  containerType?: 'sequence' | 'errorscope' | 'retryscope' | 'for' | 'foreach' | 'trycatch' | 'transaction'
                          // présent uniquement sur les nœuds nodeType==='container'
  collapsed?: boolean     // conteneur replié (réservé — collapse post-socle)
  retry?: RetryPolicy     // config Retry-scope (sur le conteneur) recopiée aux enfants
}

/** Nœud de regroupement visuel (Sequence Container & futurs types).
 *  N'a AUCUNE sémantique d'exécution : exclu du DAG et de la sérialisation YAML. */
export const CONTAINER_NODE_TYPE = 'container'
// Accepte undefined/null : les appelants passent souvent un `Map.get()`, dont
// le type est `N | undefined`. Le corps gere deja ce cas via l'acces optionnel ;
// seule la signature l'interdisait, ce qui cassait `tsc -b` sans jamais gener
// `npm run dev` (le serveur de developpement ne verifie pas les types).
export const isContainerNode = (
  n: { data?: { nodeType?: unknown } } | null | undefined,
): boolean => (n?.data?.nodeType as string) === CONTAINER_NODE_TYPE

/** Edge « proxy » d'un conteneur replié — visuel uniquement, jamais sérialisé. */
export const PROXY_EDGE_PREFIX = '__cproxy__'
export const isProxyEdge = (e: { id?: string }): boolean =>
  typeof e?.id === 'string' && e.id.startsWith(PROXY_EDGE_PREFIX)

// ── Flow → YAML ───────────────────────────────────────────────────────────────

/**
 * Convertit un graphe React Flow en structure WorkflowYAML.
 * @throws si le graphe est invalide (cycle, référence inconnue, etc.)
 */
export function flowToWorkflow(
  allNodes: Node<FlowNodeData>[],
  allEdges: Edge[],
  meta: { name: string; triggerType: 'manual' | 'schedule' | 'webhook'; cron?: string }
): WorkflowYAML {
  // Error-scope : recopier la politique on_failure du conteneur sur ses enfants
  // (héritage résolu ICI ; l'override explicite d'un enfant reste prioritaire).
  const scopeOnFailure = new Map<string, WorkflowStep['on_failure']>()
  for (const c of allNodes) {
    const cd = c.data as FlowNodeData
    if (isContainerNode(c) && cd.containerType === 'errorscope') {
      const pol = cd.onFailure
      if (pol && pol !== 'fail') {
        for (const child of allNodes) {
          if ((child as { parentId?: string }).parentId === c.id) scopeOnFailure.set(child.id, pol)
        }
      }
    }
  }

  // Retry-scope : recopier la politique retry du conteneur sur ses enfants.
  const scopeRetry = new Map<string, RetryPolicy>()
  for (const c of allNodes) {
    const cd = c.data as FlowNodeData
    if (isContainerNode(c) && cd.containerType === 'retryscope') {
      const rp = cd.retry
      if (rp && rp.max > 0) {
        for (const child of allNodes) {
          if ((child as { parentId?: string }).parentId === c.id) scopeRetry.set(child.id, rp)
        }
      }
    }
  }

  // Conteneurs + edges proxy sont purement visuels : jamais dans le workflow.yaml.
  const nodes = allNodes.filter(n => !isContainerNode(n))
  const edges = allEdges.filter(e => !isProxyEdge(e))
  if (nodes.length === 0) {
    return {
      version: '1.0',
      workflow: { name: meta.name, trigger: { type: meta.triggerType, cron: meta.cron }, steps: [] },
    }
  }

  // Construire le DAG et valider
  const dagNodes = edgesToDAGNodes(nodes.map(n => n.id), edges.map(e => ({ source: e.source, target: e.target })))
  const validation = validateDAG(dagNodes)
  if (!validation.valid) {
    throw new Error(`Invalid workflow: ${validation.errors.join(', ')}`)
  }

  // Ordre d'exécution
  const order = topologicalSort(dagNodes)

  // Mapping id → node
  const nodeMap = new Map(nodes.map(n => [n.id, n]))
  // Mapping id → depends_on noms (step names, pas IDs React Flow)
  const dagMap = new Map(dagNodes.map(d => [d.id, d]))

  const steps: WorkflowStep[] = order.map(id => {
    const rfNode = nodeMap.get(id)!
    const dag    = dagMap.get(id)!
    const data   = rfNode.data

    const step: WorkflowStep = {
      name: data.stepName ?? id,
      type: data.jobPath ? 'job' : 'action',
    }

    if (step.type === 'job' && data.jobPath) {
      step.job = data.jobPath as string
    } else {
      // Priorité : data.action explicite ; sinon extraire depuis nodeType (action_powershell → powershell)
      const nt = (data.nodeType as string) ?? ''
      const actionType = (data.action as string)
        ?? (nt.startsWith('action_') ? nt.replace('action_', '') : 'webhook')
      step.action = actionType
      if (data.params && Object.keys(data.params as object).length > 0) {
        step.params = data.params as Record<string, unknown>
      }
    }

    if (dag.dependsOn.length > 0) {
      // Résoudre les IDs React Flow → stepNames
      step.depends_on = dag.dependsOn.map(depId => {
        const depNode = nodeMap.get(depId)
        return depNode?.data.stepName ?? depId
      })
    }

    // Effectif = override explicite de l'enfant, sinon politique du conteneur Error-scope
    const effOnFailure = (data.onFailure && data.onFailure !== 'fail')
      ? data.onFailure
      : scopeOnFailure.get(id)
    if (effOnFailure && effOnFailure !== 'fail') {
      step.on_failure = effOnFailure as WorkflowStep['on_failure']
    }

    // Effectif retry = retry propre du nœud, sinon politique du Retry-scope
    const effRetry = (data.retry && data.retry.max > 0) ? data.retry : scopeRetry.get(id)
    if (effRetry && effRetry.max > 0) {
      step.retry = effRetry
    }

    if (data.enabled === false) {
      step.enabled = false
    }

    if (data.when && String(data.when).trim()) {
      step.when = String(data.when).trim()
    }

    return step
  })

  return {
    version: '1.0',
    workflow: {
      name: meta.name,
      trigger: { type: meta.triggerType, cron: meta.cron },
      steps,
    },
  }
}

/**
 * Sérialise en YAML string (format minimal compatible avec le runner Hydra).
 * Pas de dépendance yaml — génération manuelle suffisante pour notre schema.
 */
export function workflowToYAMLString(wf: WorkflowYAML): string {
  const trigger: Record<string, unknown> = { type: wf.workflow.trigger.type }
  if (wf.workflow.trigger.cron) trigger.cron = wf.workflow.trigger.cron

  const steps = wf.workflow.steps.map(step => {
    const s: Record<string, unknown> = { name: step.name, type: step.type }
    if (step.job)    s.job = step.job.replace(/\\/g, '/')   // chemins job en posix
    if (step.action) s.action = step.action
    if (step.params && Object.keys(step.params).length > 0) s.params = step.params
    if (step.depends_on?.length) s.depends_on = step.depends_on
    if (step.on_failure) s.on_failure = step.on_failure
    if (step.retry && step.retry.max > 0) {
      const r: Record<string, unknown> = { max: step.retry.max }
      if (step.retry.delay) r.delay = step.retry.delay
      if (step.retry.backoff && step.retry.backoff !== 'fixed') r.backoff = step.retry.backoff
      s.retry = r
    }
    if (step.enabled === false) s.enabled = false
    if (step.when) s.when = step.when
    return s
  })

  const doc = {
    version: wf.version,
    workflow: { name: wf.workflow.name, trigger, steps },
  }

  // js-yaml : sérialisation TYPÉE et sans perte — nombres, booléens, listes, objets
  // et block scalars préservés. Remplace l'ancien builder manuel qui coercait tout
  // en chaîne (String(v) -> "[object Object]") et écrasait les backslashes des valeurs.
  return yamlDump(doc, {
    lineWidth: -1,      // pas de repli de ligne (préserve les longues valeurs)
    noRefs: true,       // pas d'ancres/alias YAML
    sortKeys: false,    // conserve l'ordre d'insertion
    quotingType: '"',
    skipInvalid: true,  // ignore les valeurs undefined plutôt que d'échouer
  })
}

// ── YAML string → WorkflowYAML ───────────────────────────────────────────────

/**
 * Parse un YAML Hydra workflow via js-yaml (support complet : block scalars,
 * listes multi-lignes, quoting, retry, etc.).
 * Retourne null si le texte est invalide ou vide.
 */
export function parseWorkflowYAML(text: string): WorkflowYAML | null {
  if (!text.trim()) return null
  try {
    const doc = yamlLoad(text) as Record<string, unknown> | null
    const wf = (doc as { workflow?: Record<string, unknown> } | null)?.workflow
    if (!wf || typeof wf !== 'object') return null

    const trigRaw = (wf.trigger ?? {}) as Record<string, unknown>
    const trigType = ['manual', 'schedule', 'webhook'].includes(String(trigRaw.type))
      ? String(trigRaw.type) as WorkflowYAML['workflow']['trigger']['type']
      : 'manual'

    const stepsRaw = Array.isArray(wf.steps) ? wf.steps : []
    const steps: WorkflowStep[] = []
    for (const raw of stepsRaw) {
      if (!raw || typeof raw !== 'object') continue
      const r = raw as Record<string, unknown>
      const name = String(r.name ?? '').trim()
      if (!name) continue
      const step: WorkflowStep = {
        name,
        type: r.type === 'job' ? 'job' : 'action',
      }
      if (r.job)    step.job    = String(r.job)
      if (r.action) step.action = String(r.action)
      if (r.params && typeof r.params === 'object' && !Array.isArray(r.params)) {
        step.params = r.params as Record<string, unknown>
      }
      if (Array.isArray(r.depends_on)) {
        step.depends_on = r.depends_on.map(d => String(d)).filter(Boolean)
      }
      if (['fail', 'skip', 'continue'].includes(String(r.on_failure))) {
        step.on_failure = String(r.on_failure) as WorkflowStep['on_failure']
      }
      if (r.enabled === false) step.enabled = false
      if (r.when !== undefined && r.when !== null && String(r.when).trim()) step.when = String(r.when)
      if (r.retry && typeof r.retry === 'object') {
        const rt = r.retry as Record<string, unknown>
        const max = Number(rt.max ?? 0)
        if (max > 0) {
          step.retry = {
            max,
            delay: rt.delay !== undefined ? Number(rt.delay) : undefined,
            backoff: rt.backoff === 'exponential' ? 'exponential' : 'fixed',
          }
        }
      }
      steps.push(step)
    }

    return {
      version: '1.0',
      workflow: {
        name: String(wf.name ?? 'workflow'),
        trigger: {
          type: trigType,
          cron: trigRaw.cron !== undefined ? String(trigRaw.cron) : undefined,
        },
        steps,
      },
    }
  } catch {
    return null
  }
}

// ── YAML → Flow ───────────────────────────────────────────────────────────────

/**
 * Convertit une structure WorkflowYAML en nodes/edges React Flow.
 * Layout automatique : nœuds disposés par niveau (topological levels).
 */
export function workflowToFlow(wf: WorkflowYAML): {
  nodes: Node<FlowNodeData>[]
  edges: Edge[]
  meta: { name: string; triggerType: string; cron?: string }
} {
  const steps = wf.workflow.steps
  const NODE_W = 200, NODE_H = 80, GAP_X = 280, GAP_Y = 120

  // Construire le mapping stepName → step pour les dépendances
  const stepMap = new Map(steps.map(s => [s.name, s]))

  // Convertir en DAGNodes (IDs = stepNames)
  const dagNodes = steps.map(s => ({
    id: s.name,
    dependsOn: s.depends_on ?? [],
  }))

  // Levels pour le layout
  let levels = new Map<string, number>()
  try {
    levels = computeLevels(dagNodes)
  } catch {
    // Si cycle, layout linéaire
    steps.forEach((s, i) => levels.set(s.name, i))
  }

  // Grouper par niveau pour positionner
  const byLevel = new Map<number, string[]>()
  for (const [id, lvl] of levels) {
    if (!byLevel.has(lvl)) byLevel.set(lvl, [])
    byLevel.get(lvl)!.push(id)
  }

  const nodes: Node<FlowNodeData>[] = steps.map(step => {
    const lvl   = levels.get(step.name) ?? 0
    const peers = byLevel.get(lvl) ?? [step.name]
    const idx   = peers.indexOf(step.name)
    const x     = lvl * GAP_X + 50
    const y     = idx * (NODE_H + GAP_Y) + 50

    return {
      id:       step.name,
      type:     'hydraNode',  // toujours hydraNode — seul type enregistré dans NODE_TYPES
      position: { x, y },
      data: {
        label:    step.name,
        // 'job' → icône Briefcase générique ; action_xxx → icône selon type
        nodeType:  step.type === 'job' ? 'job' : `action_${step.action ?? 'webhook'}`,
        stepName:  step.name,
        jobPath:   step.job,
        action:    step.action,
        params:    step.params,
        onFailure: step.on_failure,
        enabled:   step.enabled !== false,
        when:      step.when,
      },
    }
  })

  const edges: Edge[] = []
  for (const step of steps) {
    for (const dep of step.depends_on ?? []) {
      edges.push({
        id:     `${dep}->${step.name}`,
        source: dep,
        target: step.name,
        animated: false,
      })
    }
  }

  return {
    nodes,
    edges,
    meta: { name: wf.workflow.name, triggerType: wf.workflow.trigger.type, cron: wf.workflow.trigger.cron },
  }
}
