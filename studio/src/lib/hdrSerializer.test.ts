import { describe, it, expect } from 'vitest'
import {
  jobModelToSectionYamls,
  sectionYamlsToJobModel,
  jobModelToFlow,
  type HydraJobModel,
} from './hdrSerializer'

/**
 * Round-trip d'un JOB : modèle → 4 YAML → modèle.
 * Couvre : sources multiples (join/merge), transformations variées,
 * destinations multiples, et la FIDÉLITÉ DES TYPES (nombres, listes, objets).
 */
const model: HydraJobModel = {
  name: 'sales_job',
  sources: {
    orders: {
      type: 'csv',
      connection: { path: 'data/orders.csv', delimiter: ';' },
      extract: { table: 'orders', batch_size: 5000 },     // number à préserver
    },
    refs: {
      type: 'mysql',
      connection: { host: 'db', port: 3306 },             // number à préserver
      extract: { query: 'SELECT * FROM refs' },
    },
  },
  transformations: {
    steps: [
      { filter: { expr: 'amount > 0' } },
      { select: { columns: ['id', 'amount'] } },           // liste à préserver
      { join: { right: 'refs', on: 'id', how: 'left' } },
      { aggregate: { group_by: ['id'], agg: { amount: 'sum' } } },  // objet imbriqué
    ],
  },
  destinations: {
    out_csv: { type: 'csv', connection: { path: 'out/result.csv' }, load: { mode: 'overwrite' } },
    out_db:  { type: 'postgres', connection: { host: 'pg' }, load: { table: 'results', mode: 'append' } },
  },
  pipeline: { from: 'orders', to: 'out_csv', transformations: 'transformations' },
}

describe('hdrSerializer — round-trip job (4 sections YAML)', () => {
  const back = sectionYamlsToJobModel(jobModelToSectionYamls(model), model.name)!

  it('reparse sans perte', () => {
    expect(back).not.toBeNull()
  })

  it('sources multiples préservées (join/merge)', () => {
    expect(back.sources).toEqual(model.sources)
    expect(Object.keys(back.sources)).toEqual(['orders', 'refs'])
  })

  it('transformations préservées dans l’ordre', () => {
    expect(back.transformations).toEqual(model.transformations)
  })

  it('destinations multiples préservées', () => {
    expect(back.destinations).toEqual(model.destinations)
    expect(Object.keys(back.destinations)).toEqual(['out_csv', 'out_db'])
  })

  it('pipeline from/to/transformations préservés', () => {
    expect(back.pipeline.from).toBe('orders')
    expect(back.pipeline.to).toBe('out_csv')
    expect(back.pipeline.transformations).toBe('transformations')
    expect(back.name).toBe('sales_job')
  })

  it('FIDÉLITÉ DES TYPES : nombres, listes et objets ne deviennent pas des chaînes', () => {
    expect(back.sources.orders.extract.batch_size).toBe(5000)            // number
    expect(back.sources.refs.connection.port).toBe(3306)                // number
    const sel = back.transformations.steps[1].select as { columns: string[] }
    expect(Array.isArray(sel.columns)).toBe(true)                       // liste
    const agg = back.transformations.steps[3].aggregate as { agg: Record<string, string> }
    expect(agg.agg).toEqual({ amount: 'sum' })                          // objet imbriqué
  })

  it('aucun "[object Object]" dans les YAML générés', () => {
    const y = jobModelToSectionYamls(model)
    for (const section of Object.values(y)) {
      expect(section).not.toContain('[object Object]')
    }
  })
})

describe('hdrSerializer — jobModelToFlow', () => {
  const { nodes, edges } = jobModelToFlow(model)

  it('crée un nœud par source / transformation / destination', () => {
    // 2 sources + 4 transformations + 2 destinations = 8 nœuds
    expect(nodes.length).toBe(8)
  })

  it('mappe les types de connecteur vers les bons types de nœud', () => {
    const byLabel = Object.fromEntries(nodes.map(n => [n.data.label, n.data.nodeType]))
    expect(byLabel.orders).toBe('source_csv')
    expect(byLabel.refs).toBe('source_mysql')
    expect(byLabel.out_csv).toBe('dest_csv')
    expect(byLabel.out_db).toBe('dest_postgres')
  })

  it('relie les nœuds par des edges', () => {
    expect(edges.length).toBeGreaterThan(0)
  })
})
