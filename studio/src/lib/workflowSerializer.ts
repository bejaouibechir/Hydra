/**
 * workflowSerializer.ts — Conversion bidirectionnelle
 * React Flow (nodes + edges) ↔ Hydra workflow.yaml structure
 */
import type { Node, Edge } from '@xyflow/react'
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
}

// ── Flow → YAML ───────────────────────────────────────────────────────────────

/**
 * Convertit un graphe React Flow en structure WorkflowYAML.
 * @throws si le graphe est invalide (cycle, référence inconnue, etc.)
 */
export function flowToWorkflow(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  meta: { name: string; triggerType: 'manual' | 'schedule' | 'webhook'; cron?: string }
): WorkflowYAML {
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
    throw new Error(`Workflow invalide : ${validation.errors.join(', ')}`)
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

    if (data.onFailure && data.onFailure !== 'fail') {
      step.on_failure = data.onFailure as WorkflowStep['on_failure']
    }

    if (data.enabled === false) {
      step.enabled = false
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
  const lines: string[] = []
  lines.push(`version: "${wf.version}"`)
  lines.push('workflow:')
  lines.push(`  name: "${wf.workflow.name}"`)
  lines.push('  trigger:')
  lines.push(`    type: ${wf.workflow.trigger.type}`)
  if (wf.workflow.trigger.cron) {
    lines.push(`    cron: "${wf.workflow.trigger.cron}"`)
  }
  if (wf.workflow.steps.length === 0) {
    lines.push('  steps: []')
    return lines.join('\n')
  }
  lines.push('  steps:')
  for (const step of wf.workflow.steps) {
    lines.push(`    - name: "${step.name}"`)
    lines.push(`      type: ${step.type}`)
    if (step.job)    lines.push(`      job: "${step.job.replace(/\\/g, '/')}"`)
    if (step.action) lines.push(`      action: ${step.action}`)
    if (step.params) {
      lines.push('      params:')
      for (const [k, v] of Object.entries(step.params)) {
        lines.push(`        ${k}: "${String(v).replace(/\\/g, '/')}"`)
      }
    }
    if (step.depends_on?.length) {
      lines.push(`      depends_on: [${step.depends_on.map(d => `"${d}"`).join(', ')}]`)
    }
    if (step.on_failure) {
      lines.push(`      on_failure: ${step.on_failure}`)
    }
    if (step.enabled === false) {
      lines.push(`      enabled: false`)
    }
  }
  return lines.join('\n')
}

// ── YAML string → WorkflowYAML ───────────────────────────────────────────────

/**
 * Parse un YAML Hydra workflow (format fixe généré par workflowToYAMLString).
 * Pas de dépendance externe — parser ciblé sur notre schéma exact.
 * Retourne null si le texte est invalide ou vide.
 */
export function parseWorkflowYAML(text: string): WorkflowYAML | null {
  if (!text.trim()) return null
  try {
    const lines = text.split('\n')

    const unquote = (s: string): string => {
      s = s.trim()
      if (s.length >= 2 && ((s[0] === '"' && s.at(-1) === '"') || (s[0] === "'" && s.at(-1) === "'")))
        return s.slice(1, -1)
      return s
    }

    const extractVal = (trimmed: string): string => {
      const i = trimmed.indexOf(':')
      if (i < 0) return ''
      return unquote(trimmed.slice(i + 1).replace(/#.*$/, '').trim())
    }

    const result: WorkflowYAML = {
      version: '1.0',
      workflow: { name: 'workflow', trigger: { type: 'manual' }, steps: [] },
    }

    let inTrigger = false
    let inSteps   = false
    let inParams  = false
    let currentStep: Partial<WorkflowStep> | null = null

    const finishStep = () => {
      if (currentStep?.name) result.workflow.steps.push(currentStep as WorkflowStep)
      currentStep = null
    }

    for (const rawLine of lines) {
      const trimmed = rawLine.trim()
      if (!trimmed || trimmed.startsWith('#')) continue

      const indent = rawLine.search(/\S/)

      // ── Root (indent 0) ──────────────────────────────────────────────────
      if (indent === 0) {
        finishStep()
        inTrigger = false; inSteps = false; inParams = false
        // workflow: → switch context; version: → ignore
        continue
      }

      // ── Workflow body (indent 2) ─────────────────────────────────────────
      if (indent === 2) {
        if (trimmed === 'trigger:') {
          inTrigger = true; inSteps = false; continue
        }
        if (trimmed.startsWith('steps:')) {
          finishStep(); inTrigger = false; inSteps = true; inParams = false; continue
        }
        if (trimmed.startsWith('name:')) result.workflow.name = extractVal(trimmed)
        continue
      }

      // ── Trigger keys (indent 4, no list) ────────────────────────────────
      if (indent === 4 && inTrigger) {
        if (trimmed.startsWith('type:'))
          result.workflow.trigger.type = extractVal(trimmed) as WorkflowYAML['workflow']['trigger']['type']
        else if (trimmed.startsWith('cron:'))
          result.workflow.trigger.cron = extractVal(trimmed)
        continue
      }

      // ── Step list item (indent 4, "- ") ─────────────────────────────────
      if (indent === 4 && inSteps && trimmed.startsWith('- ')) {
        finishStep(); inParams = false
        currentStep = {}
        const rest = trimmed.slice(2).trim()
        if (rest.startsWith('name:')) currentStep.name = extractVal(rest)
        continue
      }

      // ── Step attribute (indent 6) ────────────────────────────────────────
      if (indent === 6 && currentStep) {
        inParams = false
        const key = trimmed.split(':')[0].trim()
        const val = extractVal(trimmed)
        switch (key) {
          case 'name':       currentStep.name = val; break
          case 'type':       currentStep.type = val as WorkflowStep['type']; break
          case 'job':        currentStep.job  = val; break
          case 'action':     currentStep.action = val; break
          case 'on_failure': currentStep.on_failure = val as WorkflowStep['on_failure']; break
          case 'enabled':    if (val === 'false') currentStep.enabled = false; break
          case 'depends_on': {
            const m = trimmed.match(/\[([^\]]*)\]/)
            if (m) currentStep.depends_on = m[1].split(',').map(s => unquote(s)).filter(Boolean)
            break
          }
          case 'params': { currentStep.params = {}; inParams = true; break }
        }
        continue
      }

      // ── Params (indent 8) ────────────────────────────────────────────────
      if (indent === 8 && currentStep && inParams) {
        const ci = trimmed.indexOf(':')
        if (ci > 0) {
          const k = trimmed.slice(0, ci).trim()
          const v = extractVal(trimmed)
          if (!currentStep.params) currentStep.params = {}
          currentStep.params[k] = v
        }
        continue
      }
    }

    finishStep()
    if (!result.workflow.name) return null
    return result
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

