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

/**
 * SQL Server — le port et l'instance nommée.
 *
 * pymssql embarque FreeTDS, qui n'interroge pas SQL Browser : Hydra le fait
 * elle-même, mais seulement si aucun port n'est donné. Écrire 1433 par défaut
 * dans le manifeste rendrait cette résolution impossible, et un utilisateur de
 * SQL Express — dont l'instance est nommée par construction — ne pourrait pas
 * se connecter. D'où ces tests : la règle est invisible à la lecture du
 * formulaire, et c'est exactement le genre de détail qu'une refonte efface.
 */
describe('hdrSerializer — SQL Server', () => {
  const modelSql: HydraJobModel = {
    name: 'sqlserver_job',
    sources: {
      instance_nommee: {
        type: 'sqlserver',
        connection: { host: 'MACHINE', instance: 'SQLEXPRESS', database: 'ventes', user: 'u', password: 'p', schema: 'ventes_dbo' },
        extract: { table: 'commandes' },
      },
      port_explicite: {
        type: 'sqlserver',
        connection: { host: '127.0.0.1', port: 14333, database: 'ventes', user: 'u', password: 'p' },
        extract: { query: 'SELECT 1' },
      },
    },
    transformations: { steps: [] },
    destinations: {
      cible: {
        type: 'mssql',
        connection: { host: 'MACHINE\\SQLEXPRESS', database: 'entrepot', user: 'u', password: 'p' },
        load: { table: 'faits', mode: 'upsert' },
      },
    },
    pipeline: { from: 'instance_nommee', to: 'cible' },
  }

  it('mappe sqlserver et son alias mssql vers les bons nœuds', () => {
    const { nodes } = jobModelToFlow(modelSql)
    const byLabel = Object.fromEntries(nodes.map(n => [n.data.label, n.data.nodeType]))
    expect(byLabel.instance_nommee).toBe('source_sqlserver')
    expect(byLabel.port_explicite).toBe('source_sqlserver')
    expect(byLabel.cible).toBe('dest_sqlserver')
  })

  it("l'instance et le schéma survivent à l'aller-retour vers le formulaire", () => {
    const { nodes } = jobModelToFlow(modelSql)
    const src = nodes.find(n => n.data.label === 'instance_nommee')!
    const p = src.data.params as Record<string, unknown>
    expect(p.instance).toBe('SQLEXPRESS')
    expect(p.schema).toBe('ventes_dbo')
    // Sans cette reprise, réenregistrer un manifeste effacerait les deux.
  })

  it('le port explicite survit à l’aller-retour', () => {
    const { nodes } = jobModelToFlow(modelSql)
    const src = nodes.find(n => n.data.label === 'port_explicite')!
    expect((src.data.params as Record<string, unknown>).port).toBe(14333)
  })

  it('un round-trip complet ne perd rien', () => {
    const back = sectionYamlsToJobModel(jobModelToSectionYamls(modelSql), 'sqlserver_job')
    expect(back).not.toBeNull()
    expect(back!.sources.instance_nommee.connection.instance).toBe('SQLEXPRESS')
    expect(back!.sources.instance_nommee.connection.port).toBeUndefined()
    expect(back!.sources.port_explicite.connection.port).toBe(14333)
    expect(back!.destinations.cible.load.mode).toBe('upsert')
  })
})
