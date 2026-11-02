import { describe, expect, it } from 'vitest'
import type { Node } from '@xyflow/react'
import {
  flowToWorkflow, parseWorkflowYAML, workflowToFlow, workflowToYAMLString,
  PROJECT_NODE_TYPE, type FlowNodeData,
} from './workflowSerializer'

const YAML = `version: "1.0"
workflow:
  name: master
  trigger: {type: manual}
  steps:
    - name: run_crm
      type: project
      project: ../crm-sync
      env: prod
      params: {since: "{{ param:run_date }}"}
      variables: {API_URL: https://x}
      workflows: [daily]
      outputs: [last_id]
      isolation: subprocess
      timeout: 30m
      overlap: skip
    - name: after
      type: action
      action: log
      params: {message: "{{ project:run_crm.status }}"}
      depends_on: [run_crm]
`

describe('type: project step', () => {
  it('YAML → nodes → YAML keeps every field', () => {
    const wf = parseWorkflowYAML(YAML)!
    const { nodes, edges, meta } = workflowToFlow(wf)
    const n = nodes.find(x => x.id === 'run_crm')!
    expect(n.data.nodeType).toBe(PROJECT_NODE_TYPE)
    expect(n.data.projectStep).toMatchObject({ project: '../crm-sync', env: 'prod', outputs: ['last_id'], displayName: 'crm-sync' })
    const back = flowToWorkflow(nodes, edges, { name: meta.name, triggerType: 'manual' })
    const step = back.workflow.steps.find(s => s.name === 'run_crm')!
    expect(step).toMatchObject({
      type: 'project', project: '../crm-sync', env: 'prod', workflows: ['daily'], outputs: ['last_id'],
      isolation: 'subprocess', timeout: '30m', overlap: 'skip',
      params: { since: '{{ param:run_date }}' }, variables: { API_URL: 'https://x' },
    })
    expect((step as unknown as Record<string, unknown>).displayName).toBeUndefined()
    const text = workflowToYAMLString(back)
    expect(text).toContain('type: project')
    expect(text).toContain('project: ../crm-sync')
    expect(text).not.toContain('displayName')
    expect(text).not.toContain('action:\n')
  })

  it('defaults are not written', () => {
    const nodes: Node<FlowNodeData>[] = [{
      id: 'p', type: 'hydraNode', position: { x: 0, y: 0 },
      data: { label: 'crm', nodeType: PROJECT_NODE_TYPE, stepName: 'p',
        projectStep: { project: '..\\crm', ref: 'path', env: 'inherit', isolation: 'inprocess', overlap: 'wait',
                       workflows: [], outputs: [], variables: {} } },
    }]
    const step = flowToWorkflow(nodes, [], { name: 'm', triggerType: 'manual' }).workflow.steps[0]
    expect(step).toEqual({ name: 'p', type: 'project', project: '..\\crm' })
    expect(workflowToYAMLString(flowToWorkflow(nodes, [], { name: 'm', triggerType: 'manual' }))).toContain('project: ../crm')
  })
})
