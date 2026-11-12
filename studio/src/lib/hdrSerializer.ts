/**
 * hdrSerializer.ts — Format .hdr (Hydra Data Recipe)
 *
 * Bidirectionnel :
 *   flowToHdr(nodes, edges, name)       → YAML string (.hdr monolithique, legacy)
 *   parseHdr(text)                      → { nodes, edges, name } pour React Flow
 *   isHdrYaml(text)                     → true si YAML contient "job:" (vs "workflow:")
 *
 * Format multi-sections (DevOps-first) :
 *   flowToJobModel(nodes, edges, name)  → HydraJobModel
 *   jobModelToSectionYamls(model)       → JobSectionYamls (4 onglets)
 *   sectionYamlsToJobModel(yamls,name)  → HydraJobModel | null
 *   jobModelToFlow(model)               → { nodes, edges }
 */
import * as YAML from 'js-yaml'
import type { Node, Edge } from '@xyflow/react'
import { isProxyEdge, type FlowNodeData } from './workflowSerializer'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface HdrDoc {
  version: string
  job: {
    name: string
    sources:         Record<string, HdrSource>
    transformations?: { engine?: JobEngine; steps: HdrStep[] }
    destinations:    Record<string, HdrDest>
    pipeline: { from: string; to: string; transformations?: string }
  }
}

/**
 * Modèle intermédiaire — découplé du format de sérialisation.
 * Partagé entre le canvas et les 4 onglets YAML.
 */
export interface HydraJobModel {
  name:            string
  sources:         Record<string, HdrSource>
  transformations: { engine?: JobEngine; steps: HdrStep[] }
  destinations:    Record<string, HdrDest>
  pipeline:        { from: string; to: string; transformations?: string }
}

/** `engine:` de transformations.yaml — moteur des opérations globales. */
export type JobEngine = 'auto' | 'pandas' | 'duckdb'
export const JOB_ENGINES: JobEngine[] = ['auto', 'pandas', 'duckdb']

function _asEngine(v: unknown): JobEngine | undefined {
  const e = typeof v === 'string' ? v.trim().toLowerCase() : ''
  return (JOB_ENGINES as string[]).includes(e) ? e as JobEngine : undefined
}

/** Moteur du job porté par le canvas : paramètre `_engine` d'un nœud (posé sur
 *  la première source à l'import). Absent = non écrit dans le YAML (auto). */
export function jobEngineOf(nodes: Node<FlowNodeData>[]): JobEngine | undefined {
  for (const n of nodes) {
    const e = _asEngine((n.data?.params as Record<string, unknown> | undefined)?._engine)
    if (e) return e
  }
  return undefined
}

/** Pose le moteur du job sur la première source (et le retire des autres nœuds). */
export function withJobEngine(nodes: Node<FlowNodeData>[], engine: JobEngine | undefined): Node<FlowNodeData>[] {
  const first = nodes.find(n => String(n.data?.nodeType ?? '').startsWith('source_'))
  return nodes.map(n => {
    const params = { ...((n.data?.params ?? {}) as Record<string, unknown>) }
    const had = '_engine' in params
    delete params._engine
    if (n === first && engine) params._engine = engine
    else if (!had) return n
    return { ...n, data: { ...n.data, params } }
  })
}

/** Textes YAML des 4 sections (un par onglet) */
export interface JobSectionYamls {
  sources:         string
  transformations: string
  destinations:    string
  pipeline:        string
}

interface HdrSource {
  type:       string
  connection: Record<string, unknown>
  extract:    Record<string, unknown>
}

interface HdrDest {
  type:       string
  connection: Record<string, unknown>
  load:       Record<string, unknown>
}

type HdrStep = Record<string, unknown>

// ── Détection ─────────────────────────────────────────────────────────────────

/** Retourne true si le texte est un .hdr (job:) plutôt qu'un workflow.yaml */
export function isHdrYaml(text: string): boolean {
  return /^\s*job\s*:/m.test(text)
}

/** Retourne true si le canvas contient des nœuds job-builder (source/dest/transform inline) */
export function isJobBuilderCanvas(nodes: Node<FlowNodeData>[]): boolean {
  return nodes.some(n => {
    const t = (n.data as FlowNodeData).nodeType ?? ''
    return t.startsWith('source_') || t.startsWith('dest_')
  })
}

// ── Helpers de mapping type nœud → connecteur Hydra ──────────────────────────

const NODE_TO_CONNECTOR: Record<string, string> = {
  source_csv:      'csv',
  source_json:     'json',
  source_parquet:  'parquet',
  source_mysql:    'mysql',
  source_postgres: 'postgresql',
  source_sqlserver:'sqlserver',
  source_sqlite:   'sqlite',
  source_snowflake:'snowflake',
  source_postgres_cdc: 'postgresql_cdc',
  source_mongodb:  'mongodb',
  source_api:      'web_api',
  dest_csv:        'csv',
  dest_json:       'json',
  dest_parquet:    'parquet',
  dest_mysql:      'mysql',
  dest_postgres:   'postgresql',
  dest_sqlserver:  'sqlserver',
  dest_sqlite:     'sqlite',
  dest_snowflake:  'snowflake',
  dest_mongodb:    'mongodb',
}

const CONNECTOR_TO_SOURCE_NODE: Record<string, string> = {
  csv: 'source_csv', json: 'source_json', parquet: 'source_parquet',
  mysql: 'source_mysql', mariadb: 'source_mysql',
  postgresql: 'source_postgres', postgres: 'source_postgres',
  sqlserver: 'source_sqlserver', mssql: 'source_sqlserver',
  sqlite: 'source_sqlite',
  snowflake: 'source_snowflake',
  postgresql_cdc: 'source_postgres_cdc', postgres_cdc: 'source_postgres_cdc',
  mongodb: 'source_mongodb', web_api: 'source_api',
}

const CONNECTOR_TO_DEST_NODE: Record<string, string> = {
  csv: 'dest_csv', json: 'dest_json', parquet: 'dest_parquet',
  mysql: 'dest_mysql', mariadb: 'dest_mysql',
  postgresql: 'dest_postgres', postgres: 'dest_postgres',
  sqlserver: 'dest_sqlserver', mssql: 'dest_sqlserver',
  sqlite: 'dest_sqlite',
  snowflake: 'dest_snowflake',
  mongodb: 'dest_mongodb',
}

const OP_TO_NODE: Record<string, string> = {
  filter: 'transform_filter', select: 'transform_select',
  rename: 'transform_rename', cast: 'transform_cast',
  sort: 'transform_sort', aggregate: 'transform_aggregate',
  deduplicate: 'transform_dedupe', derive: 'transform_derive',
  calculate: 'transform_derive', join: 'transform_join',
  fill_null: 'transform_fill_null', trim: 'transform_trim', clean: 'transform_clean',
  pivot: 'transform_pivot', unpivot: 'transform_unpivot',
  transpose: 'transform_transpose',
  merge: 'transform_merge',
  union: 'transform_union',
  script: 'transform_script',
  text_to_rows: 'transform_text_to_rows',
  window: 'transform_window',
}

const NODE_TO_OP: Record<string, string> = {
  transform_filter: 'filter', transform_select: 'select',
  transform_rename: 'rename', transform_cast: 'cast',
  transform_sort: 'sort', transform_aggregate: 'aggregate',
  transform_dedupe: 'deduplicate', transform_derive: 'calculate', // runner: 'calculate' uniquement
  transform_join: 'join', transform_fill_null: 'fill_null',
  transform_trim: 'trim',
  transform_clean: 'clean', transform_pivot: 'pivot',
  transform_unpivot: 'unpivot',
  transform_transpose: 'transpose',
  transform_merge: 'merge',
  transform_union: 'union',
  transform_script: 'script',
  transform_text_to_rows: 'text_to_rows',
  transform_window: 'window',
}

// ── Flow → HDR ────────────────────────────────────────────────────────────────

/**
 * Sérialise un canvas Job Builder en YAML .hdr.
 * Les nœuds doivent contenir au moins une source et une destination.
 */
export function flowToHdr(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  jobName = 'my_job',
): string {
  if (nodes.length === 0) return ''
  edges = edges.filter(e => !isProxyEdge(e))

  const get = (id: string) => nodes.find(n => n.id === id)

  // Ordonner les nœuds selon le DAG
  const order: string[] = (() => {
    const adj = new Map<string, string[]>()
    nodes.forEach(n => adj.set(n.id, []))
    edges.forEach(e => adj.get(e.source)?.push(e.target))
    const visited = new Set<string>()
    const result: string[] = []
    const visit = (id: string) => {
      if (visited.has(id)) return
      visited.add(id)
      for (const next of adj.get(id) ?? []) visit(next)
      result.unshift(id)
    }
    nodes.forEach(n => visit(n.id))
    return result
  })()

  const sourceNodes  = order.map(id => get(id)!).filter(n => (n.data.nodeType as string).startsWith('source_'))
  const destNodes    = order.map(id => get(id)!).filter(n => (n.data.nodeType as string).startsWith('dest_'))
  const transformNodes = order.map(id => get(id)!).filter(n => (n.data.nodeType as string).startsWith('transform_') && n.data.enabled !== false)

  // Construire sources
  const sources: Record<string, HdrSource> = {}
  const srcKeyByNode = new Map<string, string>()
  for (const sn of sourceNodes) {
    const sid = `source_${(sn.data.nodeType as string).replace('source_', '')}_${sn.id.slice(-4)}`
    srcKeyByNode.set(sn.id, sid)
    const cfg = (sn.data.params ?? {}) as Record<string, unknown>
    const connType = NODE_TO_CONNECTOR[sn.data.nodeType as string] ?? 'csv'
    const isDb = !['csv', 'json', 'parquet'].includes(connType)

    const connection: Record<string, unknown> = isDb ? {
      host:     cfg.host     ?? 'localhost',
      port:     cfg.port     ?? (connType === 'postgresql' ? 5432 : 3306),
      database: cfg.database ?? '',
      user:     cfg.user     ?? '',
      password: cfg.password ?? '',
    } : {}
    if (connType === 'sqlserver') {
      // Le port n'est pas force a 1433 : laisse vide avec une instance nommee,
      // Hydra interroge SQL Browser et trouve le port dynamique lui-meme.
      // Ecrire 1433 d'office rendrait cette resolution impossible.
      if (cfg.port === undefined || cfg.port === null || cfg.port === '') delete connection.port
      if (cfg.instance) connection.instance = cfg.instance
      if (cfg.schema)   connection.schema   = cfg.schema
    }
    if (connType === 'mongodb') {
      Object.assign(connection, { uri: cfg.uri ?? 'mongodb://localhost:27017', database: cfg.database ?? '' })
      delete connection.host; delete connection.port; delete connection.user; delete connection.password
    }
    if (connType === 'web_api') {
      Object.assign(connection, { base_url: cfg.url ?? '', method: cfg.method ?? 'GET' })
    }

    const extract: Record<string, unknown> = isDb
      ? { table: cfg.query ? undefined : (cfg.table ?? ''), query: cfg.query ?? undefined, batch_size: 1000 }
      : connType === 'mongodb'
        ? { collection: cfg.collection ?? '', batch_size: 1000 }
        : connType === 'web_api'
          ? { endpoint: cfg.url ?? '', batch_size: 1000 }
          : { table: cfg.path ?? '', batch_size: 1000 }

    // Nettoyer les undefined
    Object.keys(extract).forEach(k => extract[k] === undefined && delete extract[k])

    if (connType === 'sqlite') {
      const sq = _sqliteSource(cfg, 1000)
      sources[sid] = { type: connType, connection: sq.connection, extract: sq.extract }
      continue
    }
    if (connType === 'snowflake') {
      const sf = _snowflakeSource(cfg, 1000)
      sources[sid] = { type: connType, connection: sf.connection, extract: sf.extract }
      continue
    }
    if (connType === 'postgresql_cdc') {
      const cd = _cdcSource(cfg, undefined)
      sources[sid] = { type: connType, connection: cd.connection, extract: cd.extract }
      continue
    }
    sources[sid] = { type: connType, connection, extract }
  }

  // Construire transformations (params UI → format moteur)
  const steps: HdrStep[] = transformNodes.map(tn => {
    const op  = NODE_TO_OP[tn.data.nodeType as string] ?? 'filter'
    const cfg = (tn.data.params ?? {}) as Record<string, unknown>
    if (op === 'join') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { join: _joinToEngine(rightKey, cfg) }
    }
    if (op === 'merge') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { merge: { right: rightKey, key: cfg.key ?? '', delete_unmatched: cfg.delete_unmatched === true || cfg.delete_unmatched === 'true' } }
    }
    if (op === 'union') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { union: { right: rightKey, distinct: cfg.distinct === true || cfg.distinct === 'true' } }
    }
    return { [op]: _uiParamsToEngine(op, cfg) }
  })

  // 'from' = source gauche (celle qui n'est le 'right' d'aucun join/merge)
  const joinRightKeys = new Set(
    steps
      .filter(st => (st as Record<string, unknown>).join || (st as Record<string, unknown>).merge || (st as Record<string, unknown>).union)
      .map(st => { const r = st as Record<string, unknown>; const o = r.join ? 'join' : (r.merge ? 'merge' : 'union'); return (st as Record<string, Record<string, unknown>>)[o].right as string })
      .filter(Boolean)
  )

  // Construire destinations
  const destinations: Record<string, HdrDest> = {}
  for (const dn of destNodes) {
    const did = `dest_${(dn.data.nodeType as string).replace('dest_', '')}_${dn.id.slice(-4)}`
    const cfg = (dn.data.params ?? {}) as Record<string, unknown>
    const connType = NODE_TO_CONNECTOR[dn.data.nodeType as string] ?? 'csv'
    const isDb = !['csv', 'json', 'parquet'].includes(connType)

    const connection: Record<string, unknown> = isDb ? {
      host:     cfg.host     ?? 'localhost',
      port:     cfg.port     ?? (connType === 'postgresql' ? 5432 : 3306),
      database: cfg.database ?? '',
      user:     cfg.user     ?? '',
      password: cfg.password ?? '',
    } : {}
    if (connType === 'sqlserver') {
      // Le port n'est pas force a 1433 : laisse vide avec une instance nommee,
      // Hydra interroge SQL Browser et trouve le port dynamique lui-meme.
      // Ecrire 1433 d'office rendrait cette resolution impossible.
      if (cfg.port === undefined || cfg.port === null || cfg.port === '') delete connection.port
      if (cfg.instance) connection.instance = cfg.instance
      if (cfg.schema)   connection.schema   = cfg.schema
    }
    if (connType === 'mongodb') {
      Object.assign(connection, { uri: cfg.uri ?? 'mongodb://localhost:27017', database: cfg.database ?? '' })
      delete connection.host; delete connection.port; delete connection.user; delete connection.password
    }

    const load: Record<string, unknown> = isDb
      ? { table: cfg.table ?? '', mode: cfg.mode ?? 'replace', ..._atomicLoad(cfg) }
      : connType === 'mongodb'
        ? { collection: cfg.collection ?? '', mode: cfg.mode ?? 'replace' }
        : { table: cfg.path ?? '', mode: cfg.mode ?? 'replace' }
    Object.keys(load).forEach(k => load[k] === undefined && delete load[k])

    if (connType === 'sqlite') {
      const sq = _sqliteDest(cfg)
      destinations[did] = { type: connType, connection: sq.connection, load: sq.load }
      continue
    }
    if (connType === 'snowflake') {
      const sf = _snowflakeDest(cfg)
      destinations[did] = { type: connType, connection: sf.connection, load: sf.load }
      continue
    }
    destinations[did] = { type: connType, connection, load }
  }

  const firstSrcId  = (Object.keys(sources).find(k => !joinRightKeys.has(k))) ?? Object.keys(sources)[0] ?? 'source'
  const firstDestId = Object.keys(destinations)[0] ?? 'destination'

  const doc: HdrDoc = {
    version: '1.0',
    job: {
      name: jobName,
      sources,
      ...(steps.length > 0 ? { transformations: { steps } } : {}),
      destinations,
      pipeline: {
        from: firstSrcId,
        to:   firstDestId,
        ...(steps.length > 0 ? { transformations: 'transformations' } : {}),
      },
    },
  }

  return YAML.dump(doc, { lineWidth: 120, quotingType: '"', forceQuotes: false })
}

// ── HDR → Flow ────────────────────────────────────────────────────────────────

const NODE_W = 220
const NODE_H = 80
const GAP_X  = 280
const GAP_Y  = 120

/**
 * Convertit un .hdr YAML en nœuds + edges React Flow.
 */
export function parseHdr(text: string): {
  nodes: Node<FlowNodeData>[]
  edges: Edge[]
  name:  string
} | null {
  if (!text.trim()) return null
  try {
    const doc = YAML.load(text) as HdrDoc
    if (!doc?.job) return null

    const { name, sources = {}, transformations, destinations = {}, pipeline } = doc.job
    const steps = transformations?.steps ?? []
    const nodes: Node<FlowNodeData>[] = []
    const edges: Edge[] = []

    let col = 0
    const prevIds: string[] = []

    // ── Sources ──────────────────────────────────────────────────────────────
    const srcEntries = Object.entries(sources)
    srcEntries.forEach(([srcId, src], i) => {
      const nodeType = CONNECTOR_TO_SOURCE_NODE[src.type] ?? 'source_csv'
      const nodeId   = `src_${srcId}`
      const params   = _sourceToParams(src)

      nodes.push({
        id:       nodeId,
        type:     'hydraNode',
        position: { x: col * GAP_X + 50, y: i * (NODE_H + GAP_Y) + 50 },
        data: {
          label:    src.type.toUpperCase(),
          nodeType,
          stepName: srcId,
          params,
          enabled:  true,
        } as FlowNodeData,
      })
      prevIds.push(nodeId)
    })
    col++

    // ── Transformations ───────────────────────────────────────────────────────
    steps.forEach((step, i) => {
      const op       = Object.keys(step)[0]
      const params   = _stepToParams(op, step[op] as Record<string, unknown>)
      const nodeType = OP_TO_NODE[op] ?? 'transform_filter'
      const nodeId   = `tf_${i}_${op}`
      const label    = op.charAt(0).toUpperCase() + op.slice(1)

      nodes.push({
        id:       nodeId,
        type:     'hydraNode',
        position: { x: col * GAP_X + 50, y: 50 },
        data: { label, nodeType, stepName: `${op}_${i}`, params, enabled: true } as FlowNodeData,
      })

      // Edge depuis tous les sources (1er transform) ou transform précédent
      const sources_ = i === 0 ? prevIds : [`tf_${i - 1}_${steps[i-1] ? Object.keys(steps[i-1])[0] : op}`]
      sources_.forEach(src => {
        edges.push({ id: `${src}->${nodeId}`, source: src, target: nodeId, type: 'smoothstep' })
      })
      col++
    })

    // ── Destinations ──────────────────────────────────────────────────────────
    const destEntries = Object.entries(destinations)
    destEntries.forEach(([destId, dest], i) => {
      const nodeType = CONNECTOR_TO_DEST_NODE[dest.type] ?? 'dest_csv'
      const nodeId   = `dst_${destId}`
      const params   = _destToParams(dest)

      nodes.push({
        id:       nodeId,
        type:     'hydraNode',
        position: { x: col * GAP_X + 50, y: i * (NODE_H + GAP_Y) + 50 },
        data: {
          label:    dest.type.toUpperCase(),
          nodeType,
          stepName: destId,
          params,
          enabled:  true,
        } as FlowNodeData,
      })

      // Edge depuis dernier transform ou source
      const lastTransformId = steps.length > 0
        ? `tf_${steps.length - 1}_${Object.keys(steps[steps.length - 1])[0]}`
        : prevIds[0]

      if (lastTransformId) {
        edges.push({ id: `${lastTransformId}->${nodeId}`, source: lastTransformId, target: nodeId, type: 'smoothstep' })
      }
    })

    return { nodes, edges, name: name ?? 'job' }
  } catch (e) {
    console.error('[hdrSerializer] parseHdr error:', e)
    return null
  }
}

// ── Helpers internes ──────────────────────────────────────────────────────────

function _parseList(v: string | string[] | undefined): string[] {
  if (!v) return []
  if (Array.isArray(v)) return v.map(String)
  return String(v).split(',').map(s => s.trim()).filter(Boolean)
}

function _parseJson(v: string | Record<string, unknown> | undefined): Record<string, unknown> {
  if (!v) return {}
  if (typeof v === 'object') return v
  try { return JSON.parse(v) } catch { return {} }
}

/** Convertit les params UI (strings saisies / valeurs YAML) vers le format
 *  attendu par le MOTEUR : listes réelles, dicts réels — jamais de JSON string.
 *  C'est la direction canvas → disk ; _stepToParams fait l'inverse (disk → UI). */
function _uiParamsToEngine(op: string, cfg: Record<string, unknown>): Record<string, unknown> {
  switch (op) {
    case 'filter':      return { expr: cfg.expr ?? '' }
    case 'select':      return { columns: _parseList(cfg.columns as string) }
    case 'rename':      return { mapping: _parseJson(cfg.mapping as string) }
    case 'cast':        return { mapping: _parseJson(cfg.mapping as string) }
    case 'sort':        return { by: _parseList(cfg.by as string), ascending: cfg.ascending !== 'DESC' && cfg.ascending !== 'false' && cfg.ascending !== false }
    case 'aggregate':   return { by: _parseList(cfg.by as string), agg: _parseJson(cfg.agg as string) }
    case 'deduplicate': {
      const cols = _parseList((cfg.columns ?? cfg.subset) as string)
      return cols.length ? { columns: cols } : {}
    }
    case 'derive':
    case 'calculate':   return { column: cfg.column ?? '', expr: cfg.expr ?? '' }
    case 'fill_null': {
      if (cfg.columns && typeof cfg.columns === 'object') return { columns: cfg.columns as Record<string, unknown> }
      if (typeof cfg.columns === 'string' && cfg.columns.trim()) return { columns: _parseJson(cfg.columns) }
      return cfg.value != null && cfg.value !== '' ? { value: cfg.value } : {}
    }
    case 'trim':        return cfg.columns ? { columns: _parseList(cfg.columns as string) } : {}
    case 'clean':       return { columns: _parseList(cfg.columns as string), case: cfg.case ?? 'none' }
    case 'pivot':       return { index: _parseList(cfg.index as string), column: cfg.column ?? '', values: cfg.values ?? '', aggfunc: cfg.aggfunc ?? 'first' }
    case 'unpivot':     return { id_vars: _parseList(cfg.id_vars as string), value_vars: _parseList(cfg.value_vars as string), var_name: cfg.var_name ?? 'variable', value_name: cfg.value_name ?? 'value' }
    case 'transpose':   return cfg.index_col ? { index_col: cfg.index_col, header_name: cfg.header_name ?? 'column' } : { header_name: cfg.header_name ?? 'column' }
    case 'script':      return { inputs: _parseList(cfg.inputs as string), outputs: _parseJson(cfg.outputs as string), code: cfg.code ?? '', mode: cfg.mode === 'row' ? 'row' : 'vectorized' }
    case 'text_to_rows': {
      const t: Record<string, unknown> = { column: String(cfg.column ?? '').trim(), sep: cfg.sep === undefined || cfg.sep === '' ? ',' : String(cfg.sep) }
      if (_bool(cfg.regex)) t.regex = true
      if (cfg.trim !== undefined && cfg.trim !== '' && !_bool(cfg.trim)) t.trim = false
      if (_bool(cfg.keep_empty)) t.keep_empty = true
      if (String(cfg.index_column ?? '').trim()) t.index_column = String(cfg.index_column).trim()
      return t
    }
    case 'window': {
      const w: Record<string, unknown> = {}
      const part = _parseList(cfg.partition_by as string)
      if (part.length) w.partition_by = part
      const order = _orderToEngine(cfg.order_by)
      if (order.length) w.order_by = order
      w.columns = _parseJson(cfg.columns as string)
      return w
    }
    default:            return { ...cfg }
  }
}

function _bool(v: unknown): boolean {
  return v === true || v === 'true' || v === 'yes'
}

/** join : how cross = sans clé (le moteur refuse key / left_key / right_key) ;
 *  max_rows seulement avec cross. */
function _joinToEngine(rightKey: string, cfg: Record<string, unknown>): Record<string, unknown> {
  const how = String(cfg.how ?? 'inner')
  const j: Record<string, unknown> = { right: rightKey, how }
  if (how === 'cross') {
    const m = _intOf(cfg.max_rows)
    if (m !== undefined && m > 0) j.max_rows = m
    else if (_isRef(cfg.max_rows)) j.max_rows = String(cfg.max_rows).trim()   // {{ param:… }} : résolu au run
    return j
  }
  if (cfg.left_key && cfg.right_key) { j.left_key = cfg.left_key; j.right_key = cfg.right_key }
  else { j.key = cfg.key ?? '' }
  return j
}

/** "order_date, amount desc" -> ["order_date", {col: "amount", desc: true}] */
function _orderToEngine(v: unknown): unknown[] {
  if (Array.isArray(v)) return v
  return String(v ?? '').split(',').map(s => s.trim()).filter(Boolean).map(item => {
    const m = item.match(/^(.+?)\s+(asc|desc)$/i)
    if (!m) return item
    return m[2].toLowerCase() === 'desc' ? { col: m[1].trim(), desc: true } : m[1].trim()
  })
}

/** Inverse : liste du YAML -> "order_date, amount desc" */
function _orderToUi(v: unknown): string {
  const items = Array.isArray(v) ? v : (v ? [v] : [])
  return items.map(it => {
    if (it && typeof it === 'object') {
      const o = it as Record<string, unknown>
      return `${o.col ?? ''}${o.desc === true ? ' desc' : ''}`
    }
    return String(it)
  }).join(', ')
}

/** load.key d'un nœud SQLite : "a, b" -> ['a', 'b'] ; vide -> undefined (la valeur du fichier est gardée). */
function _keyList(v: unknown): string[] | undefined {
  if (Array.isArray(v)) return v.map(String).filter(Boolean)
  if (typeof v !== 'string' || !v.trim()) return undefined
  return v.split(',').map(s => s.trim()).filter(Boolean)
}

/** Source / destination SQLite : connection.path, table ou query, mode, key, atomic. */
function _sqliteSource(cfg: Record<string, unknown>, batch_size: number | undefined) {
  const extract: Record<string, unknown> = cfg.query
    ? { query: cfg.query, batch_size }
    : { table: cfg.table ?? '', batch_size }
  if (batch_size === undefined) delete extract.batch_size
  return { connection: { path: cfg.path ?? '' }, extract }
}
function _sqliteDest(cfg: Record<string, unknown>) {
  const load: Record<string, unknown> = { table: cfg.table ?? '', mode: cfg.mode ?? 'replace', ..._atomicLoad(cfg) }
  const key = _keyList(cfg.key)
  if (key && key.length) load.key = key
  return { connection: { path: cfg.path ?? '' }, load }
}

/** Source Snowflake : clés de connexion non vides, table ou query. */
const SNOWFLAKE_CONN_KEYS = ['account', 'user', 'password', 'private_key_file', 'warehouse',
  'database', 'schema', 'role', 'column_case', 'json'] as const
function _snowflakeSource(cfg: Record<string, unknown>, batch_size: number | undefined) {
  const connection: Record<string, unknown> = {}
  for (const k of SNOWFLAKE_CONN_KEYS) {
    const v = cfg[k]
    if (v !== undefined && v !== null && String(v).trim() !== '') connection[k] = v
  }
  // valeurs par défaut du connecteur : inutile de les écrire
  if (connection.column_case === 'preserve') delete connection.column_case
  if (connection.json === 'parse') delete connection.json
  const extract: Record<string, unknown> = cfg.query
    ? { query: cfg.query, batch_size }
    : { table: cfg.table ?? '', batch_size }
  if (batch_size === undefined) delete extract.batch_size
  return { connection, extract }
}

/** Destination Snowflake (0.21) : clés de connexion non vides ; table, mode, key, atomic. */
const SNOWFLAKE_DEST_CONN_KEYS = ['account', 'user', 'password', 'private_key_file', 'warehouse',
  'database', 'schema', 'role'] as const
function _snowflakeDest(cfg: Record<string, unknown>) {
  const connection: Record<string, unknown> = {}
  for (const k of SNOWFLAKE_DEST_CONN_KEYS) {
    const v = cfg[k]
    if (v !== undefined && v !== null && String(v).trim() !== '') connection[k] = v
  }
  const load: Record<string, unknown> = { table: cfg.table ?? '', mode: cfg.mode ?? 'replace', ..._atomicLoad(cfg) }
  const key = _keyList(cfg.key)
  if (key && key.length) load.key = key
  return { connection, load }
}

/** Source PostgreSQL CDC : connexion PostgreSQL + slot / publication ; une table. */
const CDC_CONN_KEYS = ['host', 'port', 'database', 'user', 'password', 'slot', 'publication', 'create', 'snapshot'] as const
function _cdcSource(cfg: Record<string, unknown>, batch_size: number | undefined) {
  const connection: Record<string, unknown> = {}
  for (const k of CDC_CONN_KEYS) {
    const v = cfg[k]
    if (v === undefined || v === null || String(v).trim() === '') continue
    if (k === 'create' || k === 'snapshot') {
      // défaut du connecteur : oui ; seul « no » s'écrit
      const off = v === 'no' || v === false || v === 'false'
      if (off) connection[k] = false
      continue
    }
    connection[k] = k === 'port' && /^\d+$/.test(String(v)) ? Number(v) : v
  }
  const extract: Record<string, unknown> = { table: cfg.table ?? '', batch_size }
  if (batch_size === undefined) delete extract.batch_size
  return { connection, extract }
}

function _sourceToParams(src: HdrSource): Record<string, unknown> {
  const conn = src.connection ?? {}
  const ext  = src.extract   ?? {}
  const type = src.type

  if (['csv', 'json', 'parquet'].includes(type)) {
    return { path: ext.table ?? ext.file ?? '', delimiter: conn.delimiter }
  }
  if (type === 'sqlite') {
    return { path: (conn as Record<string, unknown>).path ?? '', table: ext.table ?? '', query: ext.query ?? '' }
  }
  if (type === 'postgresql_cdc' || type === 'postgres_cdc') {
    const c = conn as Record<string, unknown>
    const out: Record<string, unknown> = { table: ext.table ?? '' }
    for (const k of CDC_CONN_KEYS) out[k] = c[k] ?? ''
    out.create = c.create === false ? 'no' : 'yes'
    out.snapshot = c.snapshot === false ? 'no' : 'yes'
    return out
  }
  if (type === 'snowflake') {
    const c = conn as Record<string, unknown>
    const out: Record<string, unknown> = { table: ext.table ?? '', query: ext.query ?? '' }
    for (const k of SNOWFLAKE_CONN_KEYS) out[k] = c[k] ?? ''
    if (!out.column_case) out.column_case = 'preserve'
    if (!out.json) out.json = 'parse'
    return out
  }
  if (type === 'mongodb') {
    return { uri: conn.uri, database: conn.database, collection: ext.collection, filter: ext.filter ? JSON.stringify(ext.filter) : '' }
  }
  if (type === 'web_api') {
    return { url: (conn as Record<string,unknown>).base_url ?? ext.endpoint, method: (conn as Record<string,unknown>).method ?? 'GET' }
  }
  // SQL
  return { host: conn.host, port: conn.port, instance: conn.instance, schema: conn.schema,
           database: conn.database, user: conn.user, password: conn.password,
           table: ext.table ?? '', query: ext.query ?? '' }
}

function _destToParams(dest: HdrDest): Record<string, unknown> {
  const conn = dest.connection ?? {}
  const load = dest.load ?? {}
  const type = dest.type

  if (['csv', 'json', 'parquet'].includes(type)) {
    return { path: load.table ?? load.file ?? '', mode: load.mode ?? 'replace' }
  }
  if (type === 'sqlite') {
    const k = (load as Record<string, unknown>).key
    return { path: (conn as Record<string, unknown>).path ?? '', table: load.table, mode: load.mode ?? 'replace',
             key: Array.isArray(k) ? k.join(', ') : (k ?? ''),
             atomic: load.atomic === true ? 'yes' : load.atomic === false ? 'no' : 'default' }
  }
  if (type === 'snowflake') {
    const c = conn as Record<string, unknown>
    const k = (load as Record<string, unknown>).key
    const out: Record<string, unknown> = {
      table: load.table ?? '', mode: load.mode ?? 'replace',
      key: Array.isArray(k) ? k.join(', ') : (k ?? ''),
      atomic: load.atomic === true ? 'yes' : load.atomic === false ? 'no' : 'default' }
    for (const kk of SNOWFLAKE_DEST_CONN_KEYS) out[kk] = c[kk] ?? ''
    return out
  }
  if (type === 'mongodb') {
    return { uri: conn.uri, database: conn.database, collection: load.collection, mode: load.mode ?? 'replace' }
  }
  // SQL
  return { host: conn.host, port: conn.port, instance: conn.instance, schema: conn.schema,
           database: conn.database, user: conn.user, password: conn.password,
           table: load.table, mode: load.mode ?? 'replace',
           atomic: load.atomic === true ? 'yes' : load.atomic === false ? 'no' : 'default' }
}

/** load.atomic d'un nœud destination : 'yes' / 'no' → booléen ; 'default' → clé retirée.
 *  Champ absent du nœud → {} (la valeur du fichier est gardée). */
function _atomicLoad(cfg: Record<string, unknown>): Record<string, unknown> {
  if (cfg.atomic === undefined || cfg.atomic === null || cfg.atomic === '') return {}
  return { atomic: cfg.atomic === 'yes' || cfg.atomic === true ? true
    : cfg.atomic === 'no' || cfg.atomic === false ? false : undefined }
}

function _stepToParams(op: string, raw: Record<string, unknown> = {}): Record<string, unknown> {
  switch (op) {
    case 'filter':      return { expr: raw.expr ?? '' }
    case 'select':      return { columns: Array.isArray(raw.columns) ? (raw.columns as string[]).join(',') : (raw.columns ?? '') }
    case 'rename':       return { mapping: typeof raw.mapping === 'object' ? JSON.stringify(raw.mapping) : (raw.mapping ?? '') }
    case 'cast':         return { mapping: typeof raw.mapping === 'object' ? JSON.stringify(raw.mapping) : (raw.mapping ?? '') }
    case 'aggregate':    return { by: Array.isArray(raw.by) ? (raw.by as string[]).join(',') : (raw.by ?? ''), agg: typeof raw.agg === 'object' ? JSON.stringify(raw.agg) : (raw.agg ?? '') }
    case 'sort':         return { by: Array.isArray(raw.by) ? (raw.by as string[]).join(',') : (raw.by ?? ''), ascending: raw.ascending === false ? 'DESC' : 'ASC' }
    case 'derive':
    case 'calculate':    return { column: raw.column ?? '', expr: raw.expr ?? '' }
    case 'deduplicate': {
      const cols = raw.columns ?? raw.subset
      return { columns: Array.isArray(cols) ? (cols as string[]).join(',') : (cols ?? '') }
    }
    case 'join':         return { right: raw.right ?? '', key: raw.key ?? '', left_key: raw.left_key ?? '', right_key: raw.right_key ?? '', how: raw.how ?? 'inner', max_rows: raw.max_rows != null ? String(raw.max_rows) : '' }
    case 'text_to_rows': return { column: raw.column ?? '', sep: raw.sep ?? ',', regex: raw.regex === true ? 'true' : 'false', trim: raw.trim === false ? 'false' : 'true', keep_empty: raw.keep_empty === true ? 'true' : 'false', index_column: raw.index_column ?? '' }
    case 'window':       return { partition_by: Array.isArray(raw.partition_by) ? (raw.partition_by as string[]).join(', ') : (raw.partition_by ?? ''), order_by: _orderToUi(raw.order_by), columns: typeof raw.columns === 'object' ? JSON.stringify(raw.columns) : (raw.columns ?? '') }
    case 'merge':        return { right: raw.right ?? '', key: raw.key ?? '', delete_unmatched: raw.delete_unmatched ? 'true' : 'false' }
    case 'union':        return { right: raw.right ?? '', distinct: raw.distinct ? 'true' : 'false' }
    case 'fill_null':    return { value: raw.value ?? '', columns: typeof raw.columns === 'object' ? JSON.stringify(raw.columns) : (raw.columns ?? '') }
    case 'trim':         return { columns: Array.isArray(raw.columns) ? (raw.columns as string[]).join(',') : (raw.columns ?? '') }
    case 'clean':        return { columns: Array.isArray(raw.columns) ? (raw.columns as string[]).join(',') : (raw.columns ?? ''), case: raw.case ?? 'none' }
    case 'pivot':        return { index: Array.isArray(raw.index) ? (raw.index as string[]).join(',') : (raw.index ?? ''), column: raw.column ?? '', values: raw.values ?? '', aggfunc: raw.aggfunc ?? 'first' }
    case 'unpivot':      return { id_vars: Array.isArray(raw.id_vars) ? (raw.id_vars as string[]).join(',') : (raw.id_vars ?? ''), value_vars: Array.isArray(raw.value_vars) ? (raw.value_vars as string[]).join(',') : (raw.value_vars ?? ''), var_name: raw.var_name ?? 'variable', value_name: raw.value_name ?? 'value' }
    case 'transpose':    return { index_col: raw.index_col ?? '', header_name: raw.header_name ?? 'column' }
    case 'script':       return { inputs: Array.isArray(raw.inputs) ? (raw.inputs as string[]).join(',') : (raw.inputs ?? ''), outputs: typeof raw.outputs === 'object' ? JSON.stringify(raw.outputs) : (raw.outputs ?? ''), code: raw.code ?? '', mode: raw.mode === 'row' ? 'row' : 'vectorized' }
    default:             return {}
  }
}


// ── Flow → JobModel ───────────────────────────────────────────────────────────

/**
 * Construit un HydraJobModel depuis les nœuds/arêtes React Flow du canvas Job.
 */
// ── Fidélité disque → canvas → disque ─────────────────────────────────────────
// Un nœud reconstruit depuis les YAML (jobModelToFlow) garde son nom de clé
// (`_key`) et sa section d'origine (`_orig`, JSON en chaîne : la boîte de
// configuration convertit les params en chaînes). À l'écriture, les champs que
// le canvas ne connaît pas (batch_size, delimiter, encoding…) sont repris de
// l'origine, et les clés (pipeline.from / to) ne sont pas renommées.

function _origOf(cfg: Record<string, unknown>): Record<string, Record<string, unknown>> {
  const raw = cfg._orig
  try {
    const o = typeof raw === 'string' ? JSON.parse(raw) : raw
    return o && typeof o === 'object' ? o as Record<string, Record<string, unknown>> : {}
  } catch { return {} }
}

/** `over` appliqué sur `base` ; une valeur undefined dans `over` retire la clé. */
function _mergeKeep(base: Record<string, unknown> | undefined, over: Record<string, unknown>): Record<string, unknown> {
  const r: Record<string, unknown> = { ...(base ?? {}) }
  for (const [k, v] of Object.entries(over)) {
    if (v === undefined) delete r[k]
    else r[k] = v
  }
  return r
}

/** Référence {{ param:… }} / ${ENV:…} / ${SECRET:…} : écrite telle quelle. */
function _isRef(v: unknown): boolean {
  return typeof v === 'string' && /\{\{\s*(param|env)\s*:|\$\{(ENV|SECRET):/.test(v)
}

function _intOf(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && /^\s*\d+\s*$/.test(v)) return Number(v)
  return undefined
}

const _KEY_RE = /^[A-Za-z0-9_][A-Za-z0-9_.\-]*$/

function _keyFor(cfg: Record<string, unknown>, fallback: string, used: Set<string>): string {
  const k = typeof cfg._key === 'string' ? cfg._key.trim() : ''
  const key = k && _KEY_RE.test(k) && !used.has(k) ? k : fallback
  used.add(key)
  return key
}

/** batch_size : valeur du canvas, sinon celle du fichier, sinon 1000 pour un nœud neuf. */
function _batchSize(cfg: Record<string, unknown>, orig: Record<string, unknown> | undefined): number | undefined {
  const v = _intOf(cfg.batch_size) ?? _intOf(orig?.batch_size)
  if (v !== undefined) return v
  return orig ? undefined : 1000
}

export function flowToJobModel(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  name = 'my_job',
): HydraJobModel {
  edges = edges.filter(e => !isProxyEdge(e))
  const get = (id: string) => nodes.find(n => n.id === id)

  // Ordre topologique
  const adj = new Map<string, string[]>()
  nodes.forEach(n => adj.set(n.id, []))
  edges.forEach(e => adj.get(e.source)?.push(e.target))
  const visited = new Set<string>()
  const order: string[] = []
  const visit = (id: string) => {
    if (visited.has(id)) return
    visited.add(id)
    for (const next of adj.get(id) ?? []) visit(next)
    order.unshift(id)
  }
  nodes.forEach(n => visit(n.id))

  const byOrder = (pred: (n: Node<FlowNodeData>) => boolean) =>
    order.map(id => get(id)!).filter(Boolean).filter(pred)

  const sourceNodes  = byOrder(n => (n.data.nodeType as string ?? '').startsWith('source_'))
  const destNodes    = byOrder(n => (n.data.nodeType as string ?? '').startsWith('dest_'))
  const transformNodes = byOrder(n => (n.data.nodeType as string ?? '').startsWith('transform_') && n.data.enabled !== false)

  // Sources
  const sources: Record<string, HdrSource> = {}
  let firstSrcKey = 'source_main'
  const srcKeyByNode = new Map<string, string>()
  const srcUsed = new Set<string>()
  for (const sn of sourceNodes) {
    const connType = NODE_TO_CONNECTOR[sn.data.nodeType as string] ?? 'csv'
    const cfg = (sn.data.params ?? {}) as Record<string, unknown>
    const orig = _origOf(cfg)
    const isDb = !['csv', 'json', 'parquet', 'web_api'].includes(connType)
    const key = _keyFor(cfg, `source_${connType}_${sn.id.slice(-4)}`, srcUsed)
    srcKeyByNode.set(sn.id, key)
    if (sourceNodes[0] === sn) firstSrcKey = key
    const connection: Record<string, unknown> = _mergeKeep(orig.connection, isDb ? {
      host: cfg.host ?? 'localhost', port: cfg.port,
      database: cfg.database ?? '', user: cfg.user ?? '', password: cfg.password ?? '',
    } : connType === 'mongodb' ? { uri: cfg.uri ?? '', database: cfg.database ?? '' }
      : connType === 'web_api' ? { base_url: cfg.url ?? '', method: cfg.method ?? 'GET' } : {})
    if (connType === 'sqlserver') {
      // Voir plus haut : pas de port force, sinon SQL Browser ne sert a rien.
      if (cfg.port === undefined || cfg.port === null || cfg.port === '') delete connection.port
      if (cfg.instance) connection.instance = cfg.instance
      if (cfg.schema)   connection.schema   = cfg.schema
    }
    const batch_size = _batchSize(cfg, orig.extract)
    const extract: Record<string, unknown> = _mergeKeep(orig.extract, isDb
      ? { table: cfg.table ?? '', query: cfg.query, batch_size }
      : connType === 'mongodb' ? { collection: cfg.collection ?? '', batch_size }
        : connType === 'web_api' ? { endpoint: cfg.url ?? '', batch_size }
          : { table: cfg.path ?? '', batch_size })
    Object.keys(extract).forEach(k => extract[k] === undefined && delete extract[k])
    if (connType === 'sqlite') {
      const sq = _sqliteSource(cfg, batch_size)
      const ex = _mergeKeep(orig.extract, sq.extract)
      // table et query s'excluent : garder celle que le nœud définit
      if (cfg.query) delete ex.table; else delete ex.query
      sources[key] = { type: connType, connection: _mergeKeep(orig.connection, sq.connection), extract: ex }
      continue
    }
    if (connType === 'snowflake') {
      const sf = _snowflakeSource(cfg, batch_size)
      const ex = _mergeKeep(orig.extract, sf.extract)
      if (cfg.query) delete ex.table; else delete ex.query
      const cx = _mergeKeep(orig.connection, sf.connection)
      // une clé vidée dans le formulaire disparaît du fichier (sauf les champs inconnus du nœud)
      for (const k of SNOWFLAKE_CONN_KEYS) if (!(k in sf.connection)) delete cx[k]
      sources[key] = { type: connType, connection: cx, extract: ex }
      continue
    }
    if (connType === 'postgresql_cdc' || connType === 'postgres_cdc') {
      const cd = _cdcSource(cfg, batch_size)
      const ex = _mergeKeep(orig.extract, cd.extract)
      delete ex.query
      const cx = _mergeKeep(orig.connection, cd.connection)
      for (const k of CDC_CONN_KEYS) if (!(k in cd.connection)) delete cx[k]
      sources[key] = { type: 'postgresql_cdc', connection: cx, extract: ex }
      continue
    }
    sources[key] = { type: connType, connection, extract }
  }
  if (Object.keys(sources).length === 0) {
    sources['source_main'] = { type: 'csv', connection: {}, extract: { table: '', batch_size: 1000 } }
  }

  // Transformations — format MOTEUR (le disk est la référence exécutable)
  const steps: HdrStep[] = transformNodes.map(tn => {
    const op = NODE_TO_OP[tn.data.nodeType as string] ?? 'filter'
    const cfg = (tn.data.params ?? {}) as Record<string, unknown>
    if (op === 'join') {
      // 'right' vient du graphe : la source choisie (rightSourceId = id de noeud)
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { join: _joinToEngine(rightKey, cfg) }
    }
    if (op === 'merge') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { merge: { right: rightKey, key: cfg.key ?? '', delete_unmatched: cfg.delete_unmatched === true || cfg.delete_unmatched === 'true' } }
    }
    if (op === 'union') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      return { union: { right: rightKey, distinct: cfg.distinct === true || cfg.distinct === 'true' } }
    }
    return { [op]: _uiParamsToEngine(op, cfg) }
  })

  // Le 'from' du pipeline = la source gauche (celle qui n'est le 'right' d'aucun join/merge)
  const joinRightKeys = new Set(
    steps
      .filter(st => (st as Record<string, unknown>).join || (st as Record<string, unknown>).merge || (st as Record<string, unknown>).union)
      .map(st => { const r = st as Record<string, unknown>; const o = r.join ? 'join' : (r.merge ? 'merge' : 'union'); return (st as Record<string, Record<string, unknown>>)[o].right as string })
      .filter(Boolean)
  )
  if (joinRightKeys.size > 0) {
    const leftSn = sourceNodes.find(sn => !joinRightKeys.has(srcKeyByNode.get(sn.id) ?? ''))
    if (leftSn) firstSrcKey = srcKeyByNode.get(leftSn.id) ?? firstSrcKey
  }

  // Destinations
  const destinations: Record<string, HdrDest> = {}
  let firstDestKey = 'dest_main'
  const dstUsed = new Set<string>()
  for (const dn of destNodes) {
    const connType = NODE_TO_CONNECTOR[dn.data.nodeType as string] ?? 'csv'
    const cfg = (dn.data.params ?? {}) as Record<string, unknown>
    const orig = _origOf(cfg)
    const isDb = !['csv', 'json', 'parquet'].includes(connType)
    const key = _keyFor(cfg, `dest_${connType}_${dn.id.slice(-4)}`, dstUsed)
    if (destNodes[0] === dn) firstDestKey = key
    const connection: Record<string, unknown> = _mergeKeep(orig.connection, isDb ? {
      host: cfg.host ?? 'localhost', port: cfg.port,
      database: cfg.database ?? '', user: cfg.user ?? '', password: cfg.password ?? '',
    } : connType === 'mongodb' ? { uri: cfg.uri ?? '', database: cfg.database ?? '' } : {})
    if (connType === 'sqlserver') {
      // Voir plus haut : pas de port force, sinon SQL Browser ne sert a rien.
      if (cfg.port === undefined || cfg.port === null || cfg.port === '') delete connection.port
      if (cfg.instance) connection.instance = cfg.instance
      if (cfg.schema)   connection.schema   = cfg.schema
    }
    const load: Record<string, unknown> = _mergeKeep(orig.load, isDb
      ? { table: cfg.table ?? '', mode: cfg.mode ?? 'replace', ..._atomicLoad(cfg) }
      : connType === 'mongodb' ? { collection: cfg.collection ?? '', mode: cfg.mode ?? 'replace' }
        : { table: cfg.path ?? '', mode: cfg.mode ?? 'replace' })
    Object.keys(load).forEach(k => load[k] === undefined && delete load[k])
    Object.keys(connection).forEach(k => connection[k] === undefined && delete connection[k])
    if (connType === 'sqlite') {
      const sq = _sqliteDest(cfg)
      const ld = _mergeKeep(orig.load, sq.load)
      Object.keys(ld).forEach(k => ld[k] === undefined && delete ld[k])
      destinations[key] = { type: connType, connection: _mergeKeep(orig.connection, sq.connection), load: ld }
      continue
    }
    if (connType === 'snowflake') {
      const sf = _snowflakeDest(cfg)
      const ld = _mergeKeep(orig.load, sf.load)
      Object.keys(ld).forEach(k => ld[k] === undefined && delete ld[k])
      const cx = _mergeKeep(orig.connection, sf.connection)
      // une clé vidée dans le formulaire disparaît du fichier (sauf les champs inconnus du nœud)
      for (const k of SNOWFLAKE_DEST_CONN_KEYS) if (!(k in sf.connection)) delete cx[k]
      if (!('key' in sf.load)) delete ld.key
      destinations[key] = { type: connType, connection: cx, load: ld }
      continue
    }
    destinations[key] = { type: connType, connection, load }
  }
  if (Object.keys(destinations).length === 0) {
    destinations['dest_main'] = { type: 'csv', connection: {}, load: { table: '', mode: 'replace' } }
    firstDestKey = 'dest_main'
  }

  const engine = jobEngineOf(nodes)
  return {
    name,
    sources,
    transformations: { ...(engine ? { engine } : {}), steps },
    destinations,
    pipeline: {
      from: firstSrcKey,
      to: firstDestKey,
      transformations: steps.length > 0 ? 'transformations' : undefined,
    },
  }
}

// ── JobModel → Section YAMLs ──────────────────────────────────────────────────

/** Sérialise le modèle en 4 sections YAML éditables séparément.
 *  Format CANONIQUE du moteur : pipeline: à la racine, version partout —
 *  un job écrit par Studio est identique à un job écrit à la main. */
export function jobModelToSectionYamls(model: HydraJobModel): JobSectionYamls {
  const pipe: Record<string, unknown> = {
    name: model.name,
    from: model.pipeline.from,
    to:   model.pipeline.to,
  }
  if (model.pipeline.transformations) pipe.transformations = 'transformations'
  return {
    sources:         YAML.dump({ version: '1.0', sources: model.sources }, { indent: 2 }),
    transformations: YAML.dump({ version: '1.0', transformations: model.transformations }, { indent: 2 }),
    destinations:    YAML.dump({ version: '1.0', destinations: model.destinations }, { indent: 2 }),
    pipeline:        YAML.dump({ version: '1.0', pipeline: pipe }, { indent: 2 }),
  }
}

// ── Section YAMLs → JobModel ──────────────────────────────────────────────────

/** Reparse les 4 sections YAML en modèle. Retourne null si une section est invalide. */
export function sectionYamlsToJobModel(yamls: JobSectionYamls, name: string): HydraJobModel | null {
  try {
    const src  = YAML.load(yamls.sources)  as { sources?: Record<string, HdrSource> }
    // Deux formes acceptées par le moteur : `transformations: {steps: [...]}`
    // (écrite par Studio) et `steps: [...]` à la racine (hdrctl init, CLI, à la
    // main). Ignorer la 2e faisait perdre les transformations à la réécriture.
    const tf   = YAML.load(yamls.transformations) as
      { transformations?: { steps?: HdrStep[]; engine?: unknown }; steps?: HdrStep[]; engine?: unknown } | null
    const dst  = YAML.load(yamls.destinations) as { destinations?: Record<string, HdrDest> }
    type PipeShape = { name?: string; from: string; to: string; transformations?: string }
    const pip  = YAML.load(yamls.pipeline) as {
      pipeline?: PipeShape                                   // format canonique
      job?: { name?: string; pipeline?: PipeShape }          // ancien format imbriqué
    }

    const sources         = src?.sources ?? {}
    const engine = _asEngine(tf?.transformations?.engine ?? tf?.engine)
    const transformations = {
      ...(engine ? { engine } : {}),
      steps: (Array.isArray(tf?.transformations?.steps) ? tf!.transformations!.steps
        : Array.isArray(tf?.steps) ? tf!.steps : []) as HdrStep[],
    }
    const destinations    = dst?.destinations ?? {}
    const rawPipe         = pip?.pipeline ?? pip?.job?.pipeline
    const pipeline        = rawPipe ?? {
      from: Object.keys(sources)[0] ?? 'source_main',
      to:   Object.keys(destinations)[0] ?? 'dest_main',
    }
    const jobName = pip?.pipeline?.name ?? pip?.job?.name ?? name
    return { name: jobName, sources, transformations, destinations, pipeline }
  } catch {
    return null
  }
}

// ── JobModel → Flow ───────────────────────────────────────────────────────────

/** Reconstruit un canvas React Flow depuis un HydraJobModel. */
export function jobModelToFlow(model: HydraJobModel): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  const nodes: Node<FlowNodeData>[] = []
  const edges: Edge[] = []
  let x = 60

  // Sources. The main flow starts from pipeline.from; the other sources only come in
  // through a join / merge / union (their « right »), drawn as an edge into that step.
  const allKeys = Object.keys(model.sources)
  const rightKeys = new Set(
    model.transformations.steps
      .map(st => { const o = Object.keys(st)[0]; const r = (st as Record<string, Record<string, unknown>>)[o]
        return ['join', 'merge', 'union'].includes(o) && r && typeof r.right === 'string' ? r.right : '' })
      .filter(k => k && k in model.sources))
  const leftKey = (model.pipeline?.from && model.pipeline.from in model.sources) ? model.pipeline.from
    : (allKeys.find(k => !rightKeys.has(k)) ?? allKeys[0])
  const srcKeys = leftKey ? [leftKey, ...allKeys.filter(k => k !== leftKey)] : allKeys
  let srcRow = 0
  for (const key of srcKeys) {
    const src = model.sources[key]
    const nodeType = CONNECTOR_TO_SOURCE_NODE[src.type] ?? 'source_csv'
    const id = `imported_src_${key}`
    const params: Record<string, unknown> = {
      ...src.connection,
      ...src.extract,
      path: src.type === 'sqlite'
        ? (src.connection as Record<string, unknown> | undefined)?.path
        : (src.extract?.table as string) ?? (src.connection as Record<string, unknown> | undefined)?.uri,
      _key: key,
      _orig: JSON.stringify({ connection: src.connection ?? {}, extract: src.extract ?? {} }),
      ...(key === srcKeys[0] && model.transformations.engine ? { _engine: model.transformations.engine } : {}),
    }
    if (src.type === 'postgresql_cdc' || src.type === 'postgres_cdc') {
      // listes yes / no du formulaire (le connecteur vaut oui par défaut)
      const c = (src.connection ?? {}) as Record<string, unknown>
      params.create = c.create === false ? 'no' : 'yes'
      params.snapshot = c.snapshot === false ? 'no' : 'yes'
    }
    // the main source on the flow line; a right source below the line, just before the
    // step that uses it, so that its edge goes up into that step instead of running
    // behind the steps of the flow line
    const useAt = model.transformations.steps.findIndex(st => {
      const o = Object.keys(st)[0]
      const r = (st as Record<string, Record<string, unknown>>)[o]
      return ['join', 'merge', 'union'].includes(o) && r?.right === key
    })
    const position = key === leftKey || useAt < 0
      ? { x: 60, y: 100 + 160 * srcRow }
      : { x: 320 + 200 * useAt - 200, y: 260 + 140 * (srcRow - 1) }
    nodes.push({
      id, type: 'hydraNode', position,
      data: { nodeType, label: key, params } as unknown as FlowNodeData,
    })
    srcRow += 1
  }
  x = 60 + 260

  // Transformations
  const prevIds: string[] = srcKeys.map(k => `imported_src_${k}`)
  let lastTfId: string | null = null
  for (let i = 0; i < model.transformations.steps.length; i++) {
    const step = model.transformations.steps[i]
    const op   = Object.keys(step)[0]
    const nodeType = OP_TO_NODE[op] ?? 'transform_filter'
    const id = `imported_tf_${i}`
    const params = _stepToParams(op, step[op] as Record<string, unknown>)
    const right = (step[op] as Record<string, unknown> | undefined)?.right
    const rightId = ['join', 'merge', 'union'].includes(op) && typeof right === 'string' && right in model.sources
      ? `imported_src_${right}` : null
    if (rightId) params.rightSourceId = rightId          // the « Right source » of the step form
    nodes.push({
      id, type: 'hydraNode', position: { x, y: 100 },
      data: { nodeType, label: op, params } as unknown as FlowNodeData,
    })
    const sourceId = lastTfId ?? prevIds[0]
    if (sourceId) edges.push({ id: `${sourceId}->${id}`, source: sourceId, target: id, animated: false })
    if (rightId) edges.push({ id: `${rightId}->${id}`, source: rightId, target: id, animated: false })
    lastTfId = id
    x += 200
  }

  // Destinations
  const destKeys = Object.keys(model.destinations)
  for (const key of destKeys) {
    const dst = model.destinations[key]
    const nodeType = CONNECTOR_TO_DEST_NODE[dst.type] ?? 'dest_csv'
    const id = `imported_dst_${key}`
    const params: Record<string, unknown> = {
      ..._destToParams(dst),
      _key: key,
      _orig: JSON.stringify({ connection: dst.connection ?? {}, load: dst.load ?? {} }),
    }
    nodes.push({
      id, type: 'hydraNode', position: { x, y: 100 },
      data: { nodeType, label: key, params } as unknown as FlowNodeData,
    })
    const sourceId = lastTfId ?? (prevIds[0] ?? null)
    if (sourceId) edges.push({ id: `${sourceId}->${id}`, source: sourceId, target: id, animated: false })
    x += 260
  }

  return { nodes, edges }
}
