/**
 * workflowImport.ts — construction du layout du canvas workflow à partir des
 * steps d'un `workflow.yaml` importé (route « Import workflow »).
 *
 * Fonction pure, extraite de ProjectDetail.tsx pour être testable seule.
 *
 * Règle centrale : TOUS les steps deviennent des nœuds, pas seulement ceux de
 * type `job`. Les steps de type `action` (log, webhook, delay, set_param,
 * assign_param, python, bash…) étaient auparavant filtrés à l'import et
 * disparaissaient donc du canvas, alors que le fichier YAML les contenait bien.
 *
 * Le mapping d'un step d'action vers un type de nœud est le même que celui de
 * `workflowToFlow()` : `action_${step.action}`, déjà enregistré au registry.
 */

export interface ImportStep {
  name: string
  type?: string
  job?: string
  action?: string
  params?: Record<string, unknown>
  depends_on?: string[] | string
  on_failure?: string
  enabled?: boolean
  when?: string
}

export interface ImportFlowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface ImportFlowEdge {
  id: string
  source: string
  target: string
  type: string
}

export interface WorkflowLayout {
  nodes: ImportFlowNode[]
  edges: ImportFlowEdge[]
  /** Steps de type job uniquement : nom du step -> identifiant de job généré. */
  stepNameToJobId: Map<string, string>
  /** Tous les steps : nom du step -> identifiant du nœud sur le canvas. */
  stepNameToNodeId: Map<string, string>
  /** Identifiant de job -> nom du step, tel qu'attendu par `job_names`. */
  jobNames: Record<string, string>
}

const GAP_X = 300
const GAP_Y = 160
const ORIGIN_X = 100
const ORIGIN_Y = 300

/** `depends_on` peut être absent, une chaîne unique ou une liste. */
export function dependenciesOf(step: ImportStep): string[] {
  if (Array.isArray(step.depends_on)) return step.depends_on
  return step.depends_on ? [step.depends_on] : []
}

/**
 * Convertit la liste des steps en nœuds et arêtes positionnés par niveau.
 *
 * `makeJobId` est injectable pour rendre la fonction déterministe en test ;
 * par défaut elle reproduit la convention historique `job_<timestamp>_<index>`.
 */
export function buildWorkflowLayout(
  steps: ImportStep[],
  makeJobId: (index: number) => string = i => `job_${Date.now()}_${i}`,
): WorkflowLayout {
  const stepNameToJobId = new Map<string, string>()
  const stepNameToNodeId = new Map<string, string>()
  const jobNames: Record<string, string> = {}

  // 1. Identifiants. Un job reçoit un identifiant généré ; une action garde son
  //    nom de step, comme le fait workflowToFlow().
  let idx = 0
  for (const step of steps) {
    if (step.type === 'job') {
      const jobId = makeJobId(idx++)
      stepNameToJobId.set(step.name, jobId)
      stepNameToNodeId.set(step.name, jobId)
      jobNames[jobId] = step.name
    } else {
      stepNameToNodeId.set(step.name, step.name)
    }
  }

  // 2. Profondeur de chaque nœud, par relaxation successive des dépendances.
  const depthMap = new Map<string, number>()
  for (const step of steps) {
    const nodeId = stepNameToNodeId.get(step.name)!
    if (dependenciesOf(step).length === 0) depthMap.set(nodeId, 0)
  }
  let changed = true
  while (changed) {
    changed = false
    for (const step of steps) {
      const nodeId = stepNameToNodeId.get(step.name)!
      const deps = dependenciesOf(step)
      if (deps.length === 0) continue
      const parentDepths = deps.map(d => depthMap.get(stepNameToNodeId.get(d) ?? '') ?? -1)
      if (parentDepths.every(d => d >= 0)) {
        const next = Math.max(...parentDepths) + 1
        if (depthMap.get(nodeId) !== next) {
          depthMap.set(nodeId, next)
          changed = true
        }
      }
    }
  }
  // Cycle ou dépendance inconnue : le nœud retombe au niveau 0 plutôt que de
  // disparaître. Un nœud mal placé se rattrape à la souris ; un nœud absent, non.
  for (const [, nodeId] of stepNameToNodeId) {
    if (!depthMap.has(nodeId)) depthMap.set(nodeId, 0)
  }

  // 3. Positions, par colonne de profondeur.
  const byDepth = new Map<number, string[]>()
  for (const [nodeId, depth] of depthMap) {
    if (!byDepth.has(depth)) byDepth.set(depth, [])
    byDepth.get(depth)!.push(nodeId)
  }
  const stepByNodeId = new Map<string, ImportStep>(
    steps.map(s => [stepNameToNodeId.get(s.name)!, s]),
  )

  const nodes: ImportFlowNode[] = []
  for (const [depth, nodeIds] of byDepth) {
    const count = nodeIds.length
    nodeIds.forEach((nodeId, i) => {
      const step = stepByNodeId.get(nodeId)
      const position = {
        x: depth * GAP_X + ORIGIN_X,
        y: (i - (count - 1) / 2) * GAP_Y + ORIGIN_Y,
      }
      if (step?.type === 'job') {
        nodes.push({
          id: nodeId,
          type: 'hydraNode',
          position,
          data: {
            label: jobNames[nodeId],
            nodeType: 'job',
            stepName: nodeId,
            jobRef: nodeId,
            onFailure: step.on_failure ?? 'fail',
            enabled: step.enabled !== false,
          },
        })
      } else {
        nodes.push({
          id: nodeId,
          type: 'hydraNode',
          position,
          data: {
            label: step?.name ?? nodeId,
            nodeType: `action_${step?.action ?? 'webhook'}`,
            stepName: step?.name ?? nodeId,
            action: step?.action,
            params: step?.params,
            onFailure: step?.on_failure,
            enabled: step?.enabled !== false,
            when: step?.when,
          },
        })
      }
    })
  }

  // 4. Arêtes, sur l'ensemble des steps.
  const edges: ImportFlowEdge[] = []
  for (const step of steps) {
    const nodeId = stepNameToNodeId.get(step.name)!
    for (const dep of dependenciesOf(step)) {
      const srcId = stepNameToNodeId.get(dep)
      if (srcId) {
        edges.push({ id: `e_${srcId}_${nodeId}`, source: srcId, target: nodeId, type: 'smoothstep' })
      }
    }
  }

  return { nodes, edges, stepNameToJobId, stepNameToNodeId, jobNames }
}
