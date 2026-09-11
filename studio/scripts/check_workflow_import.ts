/**
 * check_workflow_import.ts — verification programmatique de l'import d'un
 * workflow.yaml vers le canvas Studio.
 *
 * Lance la fonction reelle utilisee par la route « Import workflow »
 * (lib/workflowImport.ts) sur le workflow de demo parameters_demo, puis verifie
 * que chaque step du fichier est bien devenu un noeud — y compris les actions,
 * qui etaient auparavant filtrees et disparaissaient du canvas.
 *
 * Usage, depuis studio/ :
 *     npx tsx scripts/check_workflow_import.ts
 */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as yaml from 'js-yaml'
import { buildWorkflowLayout, dependenciesOf, type ImportStep } from '../src/lib/workflowImport'

const HERE = dirname(fileURLToPath(import.meta.url))
const WF = resolve(HERE, '../../test_scenarios/parameters_demo/import_bundle/workflow.yaml')

const results: Array<[boolean, string]> = []
const check = (ok: boolean, label: string) => results.push([Boolean(ok), label])

const parsed = yaml.load(readFileSync(WF, 'utf8')) as any
const steps: ImportStep[] = parsed?.workflow?.steps ?? []

check(steps.length === 7, `7 steps lus dans le YAML (trouve ${steps.length})`)

// Identifiants deterministes pour rendre la verification reproductible.
const layout = buildWorkflowLayout(steps, i => `job_TEST_${i}`)

// -- 1. Aucun step perdu ----------------------------------------------------
check(
  layout.nodes.length === steps.length,
  `un noeud par step : ${layout.nodes.length}/${steps.length}`,
)

const byStepName = new Map(layout.nodes.map(n => [String(n.data.stepName), n]))
for (const step of steps) {
  const key = step.type === 'job' ? layout.stepNameToJobId.get(step.name)! : step.name
  check(byStepName.has(key), `le step '${step.name}' est present sur le canvas`)
}

// -- 2. Les actions portent le bon type de noeud ----------------------------
const typeOf = (stepName: string) => {
  const id = layout.stepNameToNodeId.get(stepName)!
  return String(layout.nodes.find(n => n.id === id)?.data.nodeType)
}
check(typeOf('set_label') === 'action_set_param', "set_label -> action_set_param")
check(typeOf('set_region') === 'action_set_param', "set_region -> action_set_param")
check(typeOf('switch_region') === 'action_assign_param', "switch_region -> action_assign_param")
check(typeOf('announce') === 'action_log', "announce -> action_log")
check(typeOf('report') === 'action_log', "report -> action_log")
check(typeOf('filter-orders') === 'job', "filter-orders -> job")
check(typeOf('summarize-orders') === 'job', "summarize-orders -> job")

// -- 3. Les params des actions sont conserves -------------------------------
const dataOf = (stepName: string) => {
  const id = layout.stepNameToNodeId.get(stepName)!
  return layout.nodes.find(n => n.id === id)!.data
}
const setRegion = dataOf('set_region').params as Record<string, unknown> | undefined
check(setRegion?.name === 'region', "set_region conserve params.name = region")
check(setRegion?.value === 'north', "set_region conserve params.value = north")

const switchRegion = dataOf('switch_region').params as Record<string, unknown> | undefined
check(switchRegion?.value === 'south', "switch_region conserve params.value = south")

const announce = dataOf('announce').params as Record<string, unknown> | undefined
check(
  typeof announce?.message === 'string' && announce.message.includes('{{ param:region }}'),
  "announce conserve son placeholder {{ param:region }}",
)

// -- 4. Les aretes couvrent toutes les dependances --------------------------
const expectedEdges = steps.reduce((n, s) => n + dependenciesOf(s).length, 0)
check(
  layout.edges.length === expectedEdges,
  `une arete par dependance : ${layout.edges.length}/${expectedEdges}`,
)
const hasEdge = (from: string, to: string) => {
  const s = layout.stepNameToNodeId.get(from)
  const t = layout.stepNameToNodeId.get(to)
  return layout.edges.some(e => e.source === s && e.target === t)
}
check(hasEdge('announce', 'filter-orders'), "arete announce -> filter-orders")
check(hasEdge('filter-orders', 'switch_region'), "arete filter-orders -> switch_region")
check(hasEdge('switch_region', 'summarize-orders'), "arete switch_region -> summarize-orders")

// -- 5. Le layout reste lisible ---------------------------------------------
const xs = layout.nodes.map(n => n.position.x)
check(new Set(xs).size === 7, `sept colonnes distinctes (trouve ${new Set(xs).size})`)
check(
  layout.nodes.every(n => Number.isFinite(n.position.x) && Number.isFinite(n.position.y)),
  "toutes les positions sont finies",
)
check(
  Object.keys(layout.jobNames).length === 2,
  `job_names ne contient que les jobs (trouve ${Object.keys(layout.jobNames).length})`,
)

// -- 6. Cas limites ---------------------------------------------------------
const cyclic = buildWorkflowLayout(
  [
    { name: 'a', type: 'action', action: 'log', depends_on: ['b'] },
    { name: 'b', type: 'action', action: 'log', depends_on: ['a'] },
  ],
  i => `job_C_${i}`,
)
check(cyclic.nodes.length === 2, "un cycle ne fait perdre aucun noeud")

const single = buildWorkflowLayout(
  [{ name: 'solo', type: 'action', action: 'log', depends_on: 'nowhere' }],
  i => `job_S_${i}`,
)
check(single.nodes.length === 1, "une dependance inconnue ne fait pas perdre le noeud")
check(single.edges.length === 0, "une dependance inconnue ne cree pas d'arete")

const noAction = buildWorkflowLayout([{ name: 'x', type: 'action' }], i => `job_N_${i}`)
check(
  noAction.nodes[0].data.nodeType === 'action_webhook',
  "une action sans nom retombe sur action_webhook, comme workflowToFlow",
)

// -- Rapport ----------------------------------------------------------------
console.log()
console.log('  check_workflow_import.ts — route « Import workflow »')
console.log('  ' + '-'.repeat(58))
let failed = 0
for (const [ok, label] of results) {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}   ${label}`)
  if (!ok) failed++
}
console.log('  ' + '-'.repeat(58))
console.log(`  ${results.length - failed}/${results.length} verifications passent`)
console.log()
process.exit(failed ? 1 : 0)
