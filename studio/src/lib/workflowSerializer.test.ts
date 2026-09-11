import { describe, it, expect } from 'vitest'
import { parseWorkflowYAML, workflowToYAMLString, flowToWorkflow, type WorkflowYAML, type FlowNodeData } from './workflowSerializer'
import type { Node, Edge } from '@xyflow/react'

const wf: WorkflowYAML = {
  version: '1.0',
  workflow: {
    name: 'rt_test',
    trigger: { type: 'manual' },
    steps: [
      { name: 's1', type: 'action', action: 'set_param',
        params: { name: 'me', value: 'bechir', type: 'str' } },
      { name: 'py', type: 'action', action: 'python',
        params: { script: 'import os\nwith open(r"d:\\out.txt", "w") as f:\n    f.write("{{ param:me }}")\n', timeout: '60' },
        depends_on: ['s1'], on_failure: 'skip' },
      { name: 'j', type: 'job', job: './jobs/x', depends_on: ['py'],
        retry: { max: 2, delay: 1, backoff: 'exponential' } },
    ],
  },
}

describe('parseWorkflowYAML (js-yaml)', () => {
  it('round-trip préserve un script multi-lignes (block scalar)', () => {
    const yaml = workflowToYAMLString(wf)
    expect(yaml).toMatch(/script: \|/)   // block scalar (| ou |-), style agnostique
    const parsed = parseWorkflowYAML(yaml)
    expect(parsed).not.toBeNull()
    const py = parsed!.workflow.steps.find(s => s.name === 'py')!
    expect(String(py.params!.script)).toContain('import os')
    expect(String(py.params!.script)).toContain('d:\\out.txt')
    expect(String(py.params!.script)).toContain('{{ param:me }}')
  })

  it('round-trip préserve structure, depends_on, on_failure, retry', () => {
    const parsed = parseWorkflowYAML(workflowToYAMLString(wf))!
    expect(parsed.workflow.name).toBe('rt_test')
    expect(parsed.workflow.steps.map(s => s.name)).toEqual(['s1', 'py', 'j'])
    const py = parsed.workflow.steps[1]
    expect(py.depends_on).toEqual(['s1'])
    expect(py.on_failure).toBe('skip')
    const j = parsed.workflow.steps[2]
    expect(j.type).toBe('job')
    expect(j.retry).toEqual({ max: 2, delay: 1, backoff: 'exponential' })
  })

  it('yaml invalide -> null', () => {
    expect(parseWorkflowYAML('workflow: [invalid')).toBeNull()
    expect(parseWorkflowYAML('')).toBeNull()
  })

  it('quotes échappées sur une ligne', () => {
    const one: WorkflowYAML = { version: '1.0', workflow: { name: 'q', trigger: { type: 'manual' },
      steps: [{ name: 'p', type: 'action', action: 'log', params: { message: 'say "hello"' } }] } }
    const parsed = parseWorkflowYAML(workflowToYAMLString(one))!
    expect(parsed.workflow.steps[0].params!.message).toBe('say "hello"')
  })
})


// ── Round-trip FLOW → workflow.yaml ──────────────────────────────────────────

const mkNode = (id: string, data: Partial<FlowNodeData>, parentId?: string): Node<FlowNodeData> => ({
  id, type: 'hydraNode', position: { x: 0, y: 0 },
  data: { label: id, nodeType: 'action_log', stepName: id, ...data } as FlowNodeData,
  ...(parentId ? { parentId } : {}),
})

describe('flowToWorkflow — canvas → steps', () => {
  it('exclut les conteneurs, distingue job/action, préserve when & enabled', () => {
    const nodes: Node<FlowNodeData>[] = [
      mkNode('n1', { stepName: 'log1', nodeType: 'action_log', action: 'log', params: { message: 'hi' } }),
      mkNode('n2', { stepName: 'job1', nodeType: 'job', jobPath: './jobs/x' }),
      mkNode('n3', { stepName: 'hook', nodeType: 'action_webhook', action: 'webhook',
                     params: { url: 'http://x' }, when: '{{ param:go }}', enabled: false }),
      mkNode('grp', { stepName: 'grp', nodeType: 'container', containerType: 'sequence' }),
    ]
    const edges: Edge[] = [
      { id: 'e1', source: 'n1', target: 'n2' },
      { id: 'e2', source: 'n2', target: 'n3' },
    ]
    const wf = flowToWorkflow(nodes, edges, { name: 'flowtest', triggerType: 'manual' })
    expect(wf.workflow.steps.map(s => s.name)).toEqual(['log1', 'job1', 'hook'])  // conteneur exclu

    const job = wf.workflow.steps.find(s => s.name === 'job1')!
    expect(job.type).toBe('job')
    expect(job.job).toBe('./jobs/x')
    expect(job.depends_on).toEqual(['log1'])

    const log = wf.workflow.steps.find(s => s.name === 'log1')!
    expect(log.type).toBe('action')
    expect(log.action).toBe('log')
    expect(log.params).toEqual({ message: 'hi' })

    const hook = wf.workflow.steps.find(s => s.name === 'hook')!
    expect(hook.when).toBe('{{ param:go }}')
    expect(hook.enabled).toBe(false)

    // Round-trip YAML complet
    const parsed = parseWorkflowYAML(workflowToYAMLString(wf))!
    expect(parsed.workflow.steps.map(s => s.name)).toEqual(['log1', 'job1', 'hook'])
  })

  it('Error-scope : la politique on_failure du conteneur est héritée par ses enfants', () => {
    const nodes: Node<FlowNodeData>[] = [
      mkNode('scope', { stepName: 'scope', nodeType: 'container', containerType: 'errorscope', onFailure: 'skip' }),
      mkNode('c1', { stepName: 'child1', nodeType: 'action_log', action: 'log', params: { message: 'x' } }, 'scope'),
    ]
    const wf = flowToWorkflow(nodes, [], { name: 't', triggerType: 'manual' })
    expect(wf.workflow.steps.map(s => s.name)).toEqual(['child1'])   // conteneur exclu
    expect(wf.workflow.steps[0].on_failure).toBe('skip')            // hérité
  })
})
