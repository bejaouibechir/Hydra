import { describe, it, expect } from 'vitest'
import { acceptsRefs, hasRef, insertAt } from './RefPicker'
import { sectionYamlsToJobModel, jobModelToFlow, flowToJobModel, jobModelToSectionYamls } from '@/lib/hdrSerializer'

describe('RefPicker — champs concernés', () => {
  it('chemins, connexions, seuils et expressions : oui', () => {
    for (const k of ['path', 'host', 'port', 'database', 'table', 'query', 'url', 'expr', 'max_rows', 'command', 'timeout'])
      expect(acceptsRefs('any', k)).toBe(true)
  })
  it('noms de colonnes, mappings, listes à choix : non', () => {
    for (const k of ['columns', 'mapping', 'by', 'agg', 'how', 'case', 'column', 'index_column'])
      expect(acceptsRefs('any', k)).toBe(false)
    expect(acceptsRefs('any', 'host', 'select')).toBe(false)
  })
})

describe('RefPicker — insertion', () => {
  it('au curseur, à la place de la sélection, ou de toute la valeur', () => {
    expect(insertAt('data/in.csv', '{{ param:dir }}/', 0, 0)).toBe('{{ param:dir }}/data/in.csv')
    expect(insertAt('SELECT * FROM t WHERE a > 3', '{{ param:min }}', 26, 27)).toBe('SELECT * FROM t WHERE a > {{ param:min }}')
    expect(insertAt('5432', '{{ param:port }}', 2, 2, true)).toBe('{{ param:port }}')
    expect(insertAt('', '${SECRET:db.password}')).toBe('${SECRET:db.password}')
  })
  it('détection des références', () => {
    expect(hasRef('{{ param:x }}')).toBe(true)
    expect(hasRef('${ENV:HOME}/a')).toBe(true)
    expect(hasRef('{{env:X}}')).toBe(true)
    expect(hasRef('5432')).toBe(false)
  })
})

describe('références : disque → canvas → disque', () => {
  const disk = sectionYamlsToJobModel({
    sources: 'sources:\n  pg:\n    type: postgresql\n    connection:\n      host: "{{ param:db_host }}"\n      port: "{{ param:db_port }}"\n      user: ${ENV:DB_USER}\n      password: ${SECRET:db.password}\n      database: sales\n    extract:\n      query: "SELECT * FROM o WHERE amount > {{ param:min_amount }}"\n  cal:\n    type: csv\n    extract:\n      table: "{{ env:DATA_DIR }}/cal.csv"\n',
    transformations: 'steps:\n  - join: {right: cal, how: cross, max_rows: "{{ param:max_rows }}"}\n',
    destinations: 'destinations:\n  out:\n    type: csv\n    load:\n      table: "{{ param:out_dir }}/out.csv"\n      mode: replace\n',
    pipeline: 'pipeline:\n  from: pg\n  to: out\n',
  }, 'job1')!

  it('aucune référence perdue', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const asDialog = nodes.map(n => ({ ...n, data: { ...n.data, params: Object.fromEntries(Object.entries((n.data.params ?? {}) as Record<string, unknown>).map(([k, v]) => [k, String(v ?? '')])) } }))
    const back = flowToJobModel(asDialog, edges, 'job1')
    const y = jobModelToSectionYamls(back)
    for (const ref of ['{{ param:db_host }}', '{{ param:db_port }}', '${ENV:DB_USER}', '${SECRET:db.password}',
                       '{{ param:min_amount }}', '{{ env:DATA_DIR }}/cal.csv', '{{ param:out_dir }}/out.csv'])
      expect(y.sources + y.destinations).toContain(ref)
    expect(back.transformations.steps[0]).toEqual({ join: { right: 'cal', how: 'cross', max_rows: '{{ param:max_rows }}' } })
  })
})

describe('activeEnv — valeur effective d’un paramètre', () => {
  it('environnement, puis défaut, sinon rien', async () => {
    const { effectiveValue } = await import('@/lib/activeEnv')
    const decl = { rate: { type: 'float', default: 1.2 }, dir: { type: 'str' } }
    const envs = { prod: { rate: 1.5 }, dev: {} }
    expect(effectiveValue('rate', decl, envs, 'prod')).toEqual({ value: 1.5, from: 'environment' })
    expect(effectiveValue('rate', decl, envs, 'dev')).toEqual({ value: 1.2, from: 'default' })
    expect(effectiveValue('dir', decl, envs, 'dev')).toEqual({ value: undefined, from: 'none' })
  })
})
