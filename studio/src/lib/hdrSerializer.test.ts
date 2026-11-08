import { describe, it, expect } from 'vitest'
import {
  jobModelToSectionYamls,
  sectionYamlsToJobModel,
  jobModelToFlow,
  flowToJobModel,
  jobEngineOf,
  withJobEngine,
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

/**
 * Import d'un job ecrit a la main (ou par hdrctl) : YAML -> canvas -> YAML.
 * Regression du 04/10/2026 : destination CSV sans chemin (load.table copie tel quel
 * au lieu de path), calculate / trim / deduplicate vides ou transformes en filter.
 */
describe('hdrSerializer — import YAML ecrit a la main (job1)', () => {
  const model: HydraJobModel = {
    name: 'job1',
    sources: { src: { type: 'csv', connection: {}, extract: { table: 'data/in.csv' } } },
    transformations: {
      steps: [
        { cast: { mapping: { id: 'int', v: 'int' } } },
        { trim: { columns: ['name'] } },
        { deduplicate: { columns: ['id'] } },
        { calculate: { column: 'v_squared', expr: 'v * v' } },
        { filter: { expr: 'v > 2' } },
        { sort: { by: ['v_squared'], ascending: false } },
      ],
    },
    destinations: { dst: { type: 'csv', connection: {}, load: { table: 'd:\\out\\r.csv', mode: 'replace' } } },
    pipeline: { from: 'src', to: 'dst', transformations: 'transformations' },
  }
  const { nodes, edges } = jobModelToFlow(model)
  const byId = (id: string) => nodes.find(n => n.id === id)!.data as { nodeType: string; params: Record<string, unknown> }

  it('la destination CSV garde son chemin dans path (pas dans table)', () => {
    const p = byId('imported_dst_dst').params
    expect(p.path).toBe('d:\\out\\r.csv')
    expect(p.table).toBeUndefined()
  })

  it('calculate garde column et expr', () => {
    const n = byId('imported_tf_3')
    expect(n.nodeType).toBe('transform_derive')
    expect(n.params).toEqual({ column: 'v_squared', expr: 'v * v' })
  })

  it('trim reste un nœud trim', () => {
    expect(byId('imported_tf_1').nodeType).toBe('transform_trim')
  })

  it('deduplicate garde ses colonnes', () => {
    expect(byId('imported_tf_2').params.columns).toBe('id')
  })

  it('YAML -> canvas -> modele redonne le meme job', () => {
    const back = flowToJobModel(nodes, edges, 'job1')
    const steps = back.transformations.steps
    expect(steps).toEqual([
      { cast: { mapping: { id: 'int', v: 'int' } } },
      { trim: { columns: ['name'] } },
      { deduplicate: { columns: ['id'] } },
      { calculate: { column: 'v_squared', expr: 'v * v' } },
      { filter: { expr: 'v > 2' } },
      { sort: { by: ['v_squared'], ascending: false } },
    ])
    const dst = Object.values(back.destinations)[0]
    expect(dst.load.table).toBe('d:\\out\\r.csv')
    expect(dst.load.mode).toBe('replace')
  })
})

/**
 * Disque → canvas → disque (Resync from YAML, puis écriture par Studio).
 * Le canvas ne connaît pas tous les champs : ceux qu'il ignore (batch_size,
 * delimiter, encoding…) et les noms de clés doivent revenir intacts, sinon un
 * enregistrement depuis Studio écrase ce que l'utilisateur a mis dans les YAML.
 */
describe('hdrSerializer — fidélité disque → canvas → disque', () => {
  const disk = sectionYamlsToJobModel({
    sources: 'sources:\n  src_csv:\n    type: csv\n    connection:\n      delimiter: ";"\n    extract:\n      table: data/input.csv\n      batch_size: 7000\n      encoding: latin-1\n',
    transformations: 'steps: []\n',
    destinations: 'destinations:\n  dest_csv:\n    type: csv\n    load:\n      table: data/output.csv\n      mode: append\n      header: false\n',
    pipeline: 'pipeline:\n  from: src_csv\n  to: dest_csv\n',
  }, 'job1')!

  it('garde batch_size, les champs inconnus et les noms de clés', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const back = flowToJobModel(nodes, edges, 'job1')
    expect(Object.keys(back.sources)).toEqual(['src_csv'])
    expect(back.sources.src_csv.extract.batch_size).toBe(7000)
    expect(back.sources.src_csv.extract.encoding).toBe('latin-1')
    expect(back.sources.src_csv.connection.delimiter).toBe(';')
    expect(Object.keys(back.destinations)).toEqual(['dest_csv'])
    expect(back.destinations.dest_csv.load).toEqual({ table: 'data/output.csv', mode: 'append', header: false })
    expect(back.pipeline.from).toBe('src_csv')
    expect(back.pipeline.to).toBe('dest_csv')
    const y = jobModelToSectionYamls(back)
    expect(y.sources).toContain('batch_size: 7000')
    expect(y.sources).not.toContain('_orig')
    expect(y.sources).not.toContain('_key')
  })

  it('une valeur changée sur le canvas (chaîne du formulaire) est écrite en nombre', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const src = nodes.find(n => n.data.label === 'src_csv')!
    src.data = { ...src.data, params: { ...(src.data.params as Record<string, unknown>), batch_size: '250', path: 'data/other.csv' } }
    const back = flowToJobModel(nodes, edges, 'job1')
    expect(back.sources.src_csv.extract.batch_size).toBe(250)
    expect(back.sources.src_csv.extract.table).toBe('data/other.csv')
  })

  it('un nœud neuf (sans origine) garde le batch_size par défaut', () => {
    const nodes = [{ id: 'n1abcd', type: 'hydraNode', position: { x: 0, y: 0 },
      data: { nodeType: 'source_csv', label: 'CSV', params: { path: 'a.csv' } } }] as never
    const back = flowToJobModel(nodes, [], 'j')
    expect(Object.values(back.sources)[0].extract.batch_size).toBe(1000)
  })
})

describe('engine: (moteur gros volumes)', () => {
  const files = (tf: string) => ({
    sources: 'version: "1.0"\nsources:\n  orders:\n    type: csv\n    connection: {}\n    extract:\n      table: data/orders.csv\n',
    transformations: tf,
    destinations: 'version: "1.0"\ndestinations:\n  out:\n    type: csv\n    connection: {}\n    load:\n      table: out.csv\n      mode: replace\n',
    pipeline: 'version: "1.0"\npipeline:\n  name: j\n  from: orders\n  to: out\n  transformations: transformations\n',
  })
  const STEPS = '  - sort:\n      by: [amount]\n'

  it('lu à la racine ou sous transformations:, gardé par le canvas, réécrit', () => {
    for (const tf of [`engine: duckdb\nsteps:\n${STEPS}`, `transformations:\n  engine: DuckDB\n  steps:\n  ${STEPS.replace(/\n  /g, '\n    ')}`]) {
      const model = sectionYamlsToJobModel(files(tf), 'j')!
      expect(model.transformations.engine).toBe('duckdb')
      const { nodes, edges } = jobModelToFlow(model)
      expect(jobEngineOf(nodes)).toBe('duckdb')
      const back = flowToJobModel(nodes, edges, 'j')
      expect(back.transformations.engine).toBe('duckdb')
      expect(jobModelToSectionYamls(back).transformations).toContain('engine: duckdb')
    }
  })

  it('absent ou inconnu : rien d\'écrit (auto)', () => {
    for (const tf of [`steps:\n${STEPS}`, `engine: spark\nsteps:\n${STEPS}`]) {
      const model = sectionYamlsToJobModel(files(tf), 'j')!
      expect(model.transformations.engine).toBeUndefined()
      const { nodes, edges } = jobModelToFlow(model)
      expect(jobModelToSectionYamls(flowToJobModel(nodes, edges, 'j')).transformations).not.toContain('engine')
    }
  })

  it('withJobEngine : posé sur la première source, retiré avec auto', () => {
    const { nodes, edges } = jobModelToFlow(sectionYamlsToJobModel(files(`steps:\n${STEPS}`), 'j')!)
    const set = withJobEngine(nodes, 'pandas')
    expect(jobEngineOf(set)).toBe('pandas')
    expect(flowToJobModel(set, edges, 'j').transformations.engine).toBe('pandas')
    const cleared = withJobEngine(set, undefined)
    expect(jobEngineOf(cleared)).toBeUndefined()
  })
})

/**
 * join how: cross, text_to_rows, window : disque → canvas → disque, après
 * passage par la boîte de configuration (qui convertit les params en chaînes).
 */
describe('hdrSerializer — cross join, text_to_rows, window', () => {
  const disk = sectionYamlsToJobModel({
    sources: 'sources:\n  orders:\n    type: csv\n    extract:\n      table: data/orders.csv\n  cal:\n    type: csv\n    extract:\n      table: data/cal.csv\n',
    transformations: [
      'steps:',
      '  - join: {right: cal, how: cross, max_rows: 5000}',
      '  - text_to_rows: {column: tags, sep: ";", regex: false, trim: false, keep_empty: true, index_column: pos}',
      '  - window:',
      '      partition_by: [cust]',
      '      order_by: [day, {col: amount, desc: true}]',
      '      columns:',
      '        rn: {func: row_number}',
      '        prev: {func: lag, col: amount, offset: 2, default: 0}',
      '        tot: {func: sum, col: amount}',
      '',
    ].join('\n'),
    destinations: 'destinations:\n  out:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n',
    pipeline: 'pipeline:\n  from: orders\n  to: out\n',
  }, 'job1')!

  const asDialog = (nodes: ReturnType<typeof jobModelToFlow>['nodes']) => nodes.map(n => ({
    ...n, data: { ...n.data, params: Object.fromEntries(Object.entries((n.data.params ?? {}) as Record<string, unknown>).map(([k, v]) => [k, String(v ?? '')])) },
  }))

  it('les nœuds ont le bon type', () => {
    const { nodes } = jobModelToFlow(disk)
    const types = nodes.map(n => n.data.nodeType)
    expect(types).toContain('transform_join')
    expect(types).toContain('transform_text_to_rows')
    expect(types).toContain('transform_window')
  })

  it('aller-retour sans perte (types compris)', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const back = flowToJobModel(asDialog(nodes), edges, 'job1')
    expect(back.transformations.steps).toEqual([
      { join: { right: 'cal', how: 'cross', max_rows: 5000 } },
      { text_to_rows: { column: 'tags', sep: ';', trim: false, keep_empty: true, index_column: 'pos' } },
      { window: {
        partition_by: ['cust'],
        order_by: ['day', { col: 'amount', desc: true }],
        columns: { rn: { func: 'row_number' }, prev: { func: 'lag', col: 'amount', offset: 2, default: 0 }, tot: { func: 'sum', col: 'amount' } },
      } },
    ])
  })

  it('join cross : aucune clé écrite, max_rows absent sans valeur', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const j = asDialog(nodes).map(n => n.data.nodeType === 'transform_join'
      ? { ...n, data: { ...n.data, params: { ...(n.data.params as Record<string, string>), key: 'id', max_rows: '' } } } : n)
    const step = flowToJobModel(j, edges, 'job1').transformations.steps[0]
    expect(step).toEqual({ join: { right: 'cal', how: 'cross' } })
  })

  it('join non cross : max_rows jamais écrit', () => {
    const { nodes, edges } = jobModelToFlow(disk)
    const j = asDialog(nodes).map(n => n.data.nodeType === 'transform_join'
      ? { ...n, data: { ...n.data, params: { ...(n.data.params as Record<string, string>), how: 'left', key: 'id' } } } : n)
    expect(flowToJobModel(j, edges, 'job1').transformations.steps[0]).toEqual({ join: { right: 'cal', how: 'left', key: 'id' } })
  })
})

/**
 * SQLite (0.20) : connection.path (fichier), table ou query, et en destination
 * mode, key (upsert) et atomic. Le chemin vient de connection.path, pas de la
 * table comme pour les fichiers CSV / JSON / Parquet.
 */
describe('hdrSerializer — SQLite', () => {
  const modelLite: HydraJobModel = {
    name: 'sqlite_job',
    sources: {
      app: { type: 'sqlite', connection: { path: '../../data/app.db' }, extract: { table: 'orders' } },
      recent: { type: 'sqlite', connection: { path: '../../data/app.db' }, extract: { query: 'SELECT * FROM orders WHERE day > 3' } },
    },
    transformations: { steps: [] },
    destinations: {
      dw: {
        type: 'sqlite',
        connection: { path: '../../outputs/dw.db' },
        load: { table: 'orders', mode: 'upsert', key: ['order_id', 'line'], atomic: false },
      },
    },
    pipeline: { from: 'app', to: 'dw' },
  }

  it('mappe sqlite vers les nœuds SQLite', () => {
    const { nodes } = jobModelToFlow(modelLite)
    const byLabel = Object.fromEntries(nodes.map(n => [n.data.label, n.data.nodeType]))
    expect(byLabel.app).toBe('source_sqlite')
    expect(byLabel.dw).toBe('dest_sqlite')
  })

  it('le formulaire reçoit le fichier, la table, la clé et le tout ou rien', () => {
    const { nodes } = jobModelToFlow(modelLite)
    const src = nodes.find(n => n.data.label === 'app')!.data.params as Record<string, unknown>
    expect(src.path).toBe('../../data/app.db')
    expect(src.table).toBe('orders')
    const dst = nodes.find(n => n.data.label === 'dw')!.data.params as Record<string, unknown>
    expect(dst.path).toBe('../../outputs/dw.db')
    expect(dst.key).toBe('order_id, line')
    expect(dst.atomic).toBe('no')
  })

  it('canvas -> YAML : connection.path, key en liste, table XOR query', () => {
    const { nodes, edges } = jobModelToFlow(modelLite)
    const back = flowToJobModel(nodes, edges, 'sqlite_job')
    expect(back.sources.app.connection).toEqual({ path: '../../data/app.db' })
    expect(back.sources.app.extract.table).toBe('orders')
    expect(back.sources.app.extract.query).toBeUndefined()
    expect(back.sources.recent.extract.query).toBe('SELECT * FROM orders WHERE day > 3')
    expect(back.sources.recent.extract.table).toBeUndefined()
    expect(back.destinations.dw.connection).toEqual({ path: '../../outputs/dw.db' })
    expect(back.destinations.dw.load).toMatchObject({ table: 'orders', mode: 'upsert', key: ['order_id', 'line'], atomic: false })
  })

  it('un round-trip YAML complet ne perd rien', () => {
    const back = sectionYamlsToJobModel(jobModelToSectionYamls(modelLite), 'sqlite_job')
    expect(back).not.toBeNull()
    expect(back!.destinations.dw.load.key).toEqual(['order_id', 'line'])
    expect(back!.sources.recent.extract.query).toContain('SELECT')
  })
})

/**
 * Snowflake (0.20) : source en lecture seule. Les clés de connexion du
 * formulaire vont dans connection (vides retirées), table XOR query ; les
 * références ({{ env:… }}) passent telles quelles.
 */
describe('hdrSerializer — Snowflake', () => {
  const modelSf: HydraJobModel = {
    name: 'sf_job',
    sources: {
      dwh: {
        type: 'snowflake',
        connection: {
          account: '{{ env:SNOWFLAKE_ACCOUNT }}', user: 'HYDRA_SVC',
          private_key_file: '{{ env:SNOWFLAKE_PRIVATE_KEY_FILE }}', warehouse: 'COMPUTE_WH',
          database: 'SALES', schema: 'PUBLIC', column_case: 'lower',
        },
        extract: { table: 'ORDERS', batch_size: 10000 },
      },
      recent: {
        type: 'snowflake',
        connection: { account: 'acme', user: 'u', database: 'SALES', json: 'text' },
        extract: { query: 'SELECT * FROM ORDERS WHERE AMOUNT > 100' },
      },
    },
    transformations: { steps: [] },
    destinations: {
      pg: { type: 'postgresql', connection: { host: 'localhost', database: 'postgres', user: 'postgres' },
            load: { table: 'orders', mode: 'upsert', key: ['order_id'] } },
    },
    pipeline: { from: 'dwh', to: 'pg' },
  }

  it('mappe snowflake vers le nœud Snowflake', () => {
    const { nodes } = jobModelToFlow(modelSf)
    const byLabel = Object.fromEntries(nodes.map(n => [n.data.label, n.data.nodeType]))
    expect(byLabel.dwh).toBe('source_snowflake')
  })

  it('le formulaire reçoit compte, clé, base, casse et table', () => {
    const { nodes } = jobModelToFlow(modelSf)
    const p = nodes.find(n => n.data.label === 'dwh')!.data.params as Record<string, unknown>
    expect(p.account).toBe('{{ env:SNOWFLAKE_ACCOUNT }}')
    expect(p.private_key_file).toBe('{{ env:SNOWFLAKE_PRIVATE_KEY_FILE }}')
    expect(p.database).toBe('SALES')
    expect(p.column_case).toBe('lower')
    expect(p.table).toBe('ORDERS')
  })

  it('canvas -> YAML : connexion intacte, table XOR query, pas de clé vide', () => {
    const { nodes, edges } = jobModelToFlow(modelSf)
    const back = flowToJobModel(nodes, edges, 'sf_job')
    expect(back.sources.dwh.type).toBe('snowflake')
    expect(back.sources.dwh.connection).toEqual(modelSf.sources.dwh.connection)
    expect(back.sources.dwh.extract).toMatchObject({ table: 'ORDERS', batch_size: 10000 })
    expect(back.sources.dwh.extract.query).toBeUndefined()
    expect(back.sources.recent.connection).toEqual({ account: 'acme', user: 'u', database: 'SALES', json: 'text' })
    expect(back.sources.recent.extract.query).toContain('SELECT')
    expect(back.sources.recent.extract.table).toBeUndefined()
  })

  it('un champ vidé dans le formulaire disparaît du YAML', () => {
    const { nodes, edges } = jobModelToFlow(modelSf)
    const n = nodes.find(x => x.data.label === 'dwh')!
    ;(n.data.params as Record<string, unknown>).schema = ''
    const back = flowToJobModel(nodes, edges, 'sf_job')
    expect(back.sources.dwh.connection.schema).toBeUndefined()
    expect(back.sources.dwh.connection.account).toBe('{{ env:SNOWFLAKE_ACCOUNT }}')
  })

  it('un round-trip YAML complet ne perd rien', () => {
    const back = sectionYamlsToJobModel(jobModelToSectionYamls(modelSf), 'sf_job')
    expect(back).not.toBeNull()
    expect(back!.sources.dwh.connection.column_case).toBe('lower')
    expect(back!.sources.recent.extract.query).toContain('SELECT')
  })
})
