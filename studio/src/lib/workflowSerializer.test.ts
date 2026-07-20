import { describe, it, expect } from 'vitest'
import { parseWorkflowYAML, workflowToYAMLString, type WorkflowYAML } from './workflowSerializer'

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
    expect(yaml).toContain('script: |-')
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
