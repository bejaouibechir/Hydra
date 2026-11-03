import { describe, expect, it } from 'vitest'
import { configFromForm, emptyForm, formFromConfig, formProblems, type TriggerConfig } from './triggers'

describe('triggers form', () => {
  it('round-trips a config through the form', () => {
    const cases: TriggerConfig[] = [
      { name: 'nightly', type: 'cron', cron: '0 2 * * *', timezone: 'Europe/Paris', env: 'prod', workflows: ['a', 'b'], retry: { max: 2, delay: '5m' } },
      { name: 'q', type: 'interval', every: '15m', enabled: false },
      { name: 'f', type: 'file', path: 'inbox/*.csv', events: ['added', 'modified'], debounce: '2s', every: '5s' },
      { name: 'm', type: 'marker', path: 'inbox/READY', consume: false },
      { name: 's', type: 'source_change', source: { job: 'jobs/ingest', id: 'orders', check: 'max', column: 'updated_at' }, every: '1m' },
      { name: 'w', type: 'webhook', token: '${SECRET:trigger.w.token}', overlap: 'wait', timeout: '30m' },
      { name: 'a', type: 'after_project', project: '../crm', on: 'failure', params: { mode: 'x' } },
    ]
    for (const c of cases) expect(configFromForm(formFromConfig(c))).toEqual(c)
  })

  it('writes only the keys of the type, without defaults', () => {
    const f = { ...emptyForm('file', 'drop'), every: '', overlap: 'skip' as const }
    expect(configFromForm(f)).toEqual({ name: 'drop', type: 'file', path: 'inbox/*.csv' })
    const w = emptyForm('webhook', 'hook')
    expect(configFromForm(w).token).toBe('${SECRET:trigger.hook.token}')
  })

  it('reports problems before saving', () => {
    expect(formProblems(emptyForm('cron', ''), [])).toContain('A name is required.')
    expect(formProblems({ ...emptyForm('cron', 'x'), cron: '0 2 *' }, [])[0]).toMatch(/five fields/)
    expect(formProblems({ ...emptyForm('file', 'x'), path: '../a' }, [])).toContain('The path must stay inside the project.')
    expect(formProblems(emptyForm('interval', 'dup'), ['dup'])).toContain("The name 'dup' is already used.")
    expect(formProblems({ ...emptyForm('cron', 'x'), params: [{ key: 'pw', value: '${SECRET:db}' }] }, []))
      .toContain('No secret in parameters: the project reads its own secrets.')
    expect(formProblems(emptyForm('cron', 'ok'), [])).toEqual([])
  })
})
