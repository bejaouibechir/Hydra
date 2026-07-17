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
    transformations?: { steps: HdrStep[] }
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
  transformations: { steps: HdrStep[] }
  destinations:    Record<string, HdrDest>
  pipeline:        { from: string; to: string; transformations?: string }
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
  source_mongodb:  'mongodb',
  source_api:      'web_api',
  dest_csv:        'csv',
  dest_json:       'json',
  dest_parquet:    'parquet',
  dest_mysql:      'mysql',
  dest_postgres:   'postgresql',
  dest_mongodb:    'mongodb',
}

const CONNECTOR_TO_SOURCE_NODE: Record<string, string> = {
  csv: 'source_csv', json: 'source_json', parquet: 'source_parquet',
  mysql: 'source_mysql', mariadb: 'source_mysql',
  postgresql: 'source_postgres', postgres: 'source_postgres',
  mongodb: 'source_mongodb', web_api: 'source_api',
}

const CONNECTOR_TO_DEST_NODE: Record<string, string> = {
  csv: 'dest_csv', json: 'dest_json', parquet: 'dest_parquet',
  mysql: 'dest_mysql', mariadb: 'dest_mysql',
  postgresql: 'dest_postgres', postgres: 'dest_postgres',
  mongodb: 'dest_mongodb',
}

const OP_TO_NODE: Record<string, string> = {
  filter: 'transform_filter', select: 'transform_select',
  rename: 'transform_rename', cast: 'transform_cast',
  sort: 'transform_sort', aggregate: 'transform_aggregate',
  deduplicate: 'transform_dedupe', derive: 'transform_derive',
  calculate: 'transform_derive', join: 'transform_join',
  fill_null: 'transform_fill_null', clean: 'transform_clean',
  pivot: 'transform_pivot', unpivot: 'transform_unpivot',
  transpose: 'transform_transpose',
  merge: 'transform_merge',
  union: 'transform_union',
  script: 'transform_script',
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

    sources[sid] = { type: connType, connection, extract }
  }

  // Construire transformations (params UI → format moteur)
  const steps: HdrStep[] = transformNodes.map(tn => {
    const op  = NODE_TO_OP[tn.data.nodeType as string] ?? 'filter'
    const cfg = (tn.data.params ?? {}) as Record<string, unknown>
    if (op === 'join') {
      const rightKey = srcKeyByNode.get(cfg.rightSourceId as string) ?? (cfg.right as string) ?? ''
      const j: Record<string, unknown> = { right: rightKey, how: cfg.how ?? 'inner' }
      if (cfg.left_key && cfg.right_key) { j.left_key = cfg.left_key; j.right_key = cfg.right_key }
      else { j.key = cfg.key ?? '' }
      return { join: j }
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
    if (connType === 'mongodb') {
      Object.assign(connection, { uri: cfg.uri ?? 'mongodb://localhost:27017', database: cfg.database ?? '' })
      delete connection.host; delete connection.port; delete connection.user; delete connection.password
    }

    const load: Record<string, unknown> = isDb
      ? { table: cfg.table ?? '', mode: cfg.mode ?? 'replace' }
      : connType === 'mongodb'
        ? { collection: cfg.collection ?? '', mode: cfg.mode ?? 'replace' }
        : { table: cfg.path ?? '', mode: cfg.mode ?? 'replace' }

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
    default:            return { ...cfg }
  }
}

function _sourceToParams(src: HdrSource): Record<string, unknown> {
  const conn = src.connection ?? {}
  const ext  = src.extract   ?? {}
  const type = src.type

  if (['csv', 'json', 'parquet'].includes(type)) {
    return { path: ext.table ?? ext.file ?? '', delimiter: conn.delimiter }
  }
  if (type === 'mongodb') {
    return { uri: conn.uri, database: conn.database, collection: ext.collection, filter: ext.filter ? JSON.stringify(ext.filter) : '' }
  }
  if (type === 'web_api') {
    return { url: (conn as Record<string,unknown>).base_url ?? ext.endpoint, method: (conn as Record<string,unknown>).method ?? 'GET' }
  }
  // SQL
  return { host: conn.host, port: conn.port, database: conn.database, user: conn.user, password: conn.password, table: ext.table ?? '', query: ext.query ?? '' }
}

function _destToParams(dest: HdrDest): Record<string, unknown> {
  const conn = dest.connection ?? {}
  const load = dest.load ?? {}
  const type = dest.type

  if (['csv', 'json', 'parquet'].includes(type)) {
    return { path: load.table ?? load.file ?? '', mode: load.mode ?? 'replace' }
  }
  if (type === 'mongodb') {
    return { uri: conn.uri, database: conn.database, collection: load.collection, mode: load.mode ?? 'replace' }
  }
  // SQL
  return { host: conn.host, port: conn.port, database: conn.database, user: conn.user, password: conn.password, table: load.table, mode: load.mode ?? 'replace' }
}

function _stepToParams(op: string, raw: Record<string, unknown> = {}): Record<string, unknown> {
  switch (op) {
    case 'filter':      return { expr: raw.expr ?? '' }
    case 'select':      return { columns: Array.isArray(raw.columns) ? (raw.columns as string[]).join(',') : (raw.columns ?? '') }
    case 'rename':       return { mapping: typeof raw.mapping === 'object' ? JSON.stringify(raw.mapping) : (raw.mapping ?? '') }
    case 'cast':         return { mapping: typeof raw.mapping === 'object' ? JSON.stringify(raw.mapping) : (raw.mapping ?? '') }
    case 'aggregate':    return { by: Array.isArray(raw.by) ? (raw.by as string[]).join(',') : (raw.by ?? ''), agg: typeof raw.agg === 'object' ? JSON.stringify(raw.agg) : (raw.agg ?? '') }
    case 'sort':         return { by: Array.isArray(raw.by) ? (raw.by as string[]).join(',') : (raw.by ?? ''), ascending: raw.ascending === false ? 'DESC' : 'ASC' }
    case 'derive':       return { column: raw.column ?? '', expr: raw.expr ?? '' }
    case 'deduplicate':  return { subset: Array.isArray(raw.subset) ? (raw.subset as string[]).join(',') : (raw.subset ?? '') }
    case 'join':         return { right: raw.right ?? '', key: raw.key ?? '', left_key: raw.left_key ?? '', right_key: raw.right_key ?? '', how: raw.how ?? 'inner' }
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
  for (const sn of sourceNodes) {
    const connType = NODE_TO_CONNECTOR[sn.data.nodeType as string] ?? 'csv'
    const cfg = (sn.data.params ?? {}) as Record<string, unknown>
    const isDb = !['csv', 'json', 'parquet', 'web_api'].includes(connType)
    const key = `source_${connType}_${sn.id.slice(-4)}`
    srcKeyByNode.set(sn.id, key)
    if (sourceNodes[0] === sn) firstSrcKey = key
    const connection: Record<string, unknown> = isDb ? {
      host: cfg.host ?? 'localhost', port: cfg.port,
      database: cfg.database ?? '', user: cfg.user ?? '', password: cfg.password ?? '',
    } : connType === 'mongodb' ? { uri: cfg.uri ?? '', database: cfg.database ?? '' }
      : connType === 'web_api' ? { base_url: cfg.url ?? '', method: cfg.method ?? 'GET' } : {}
    const extract: Record<string, unknown> = isDb
      ? { table: cfg.table ?? '', query: cfg.query, batch_size: 1000 }
      : connType === 'mongodb' ? { collection: cfg.collection ?? '', batch_size: 1000 }
        : connType === 'web_api' ? { endpoint: cfg.url ?? '', batch_size: 1000 }
          : { table: cfg.path ?? '', batch_size: 1000 }
    Object.keys(extract).forEach(k => extract[k] === undefined && delete extract[k])
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
      const j: Record<string, unknown> = { right: rightKey, how: cfg.how ?? 'inner' }
      if (cfg.left_key && cfg.right_key) { j.left_key = cfg.left_key; j.right_key = cfg.right_key }
      else { j.key = cfg.key ?? '' }
      return { join: j }
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
  for (const dn of destNodes) {
    const connType = NODE_TO_CONNECTOR[dn.data.nodeType as string] ?? 'csv'
    const cfg = (dn.data.params ?? {}) as Record<string, unknown>
    const isDb = !['csv', 'json', 'parquet'].includes(connType)
    const key = `dest_${connType}_${dn.id.slice(-4)}`
    if (destNodes[0] === dn) firstDestKey = key
    const connection: Record<string, unknown> = isDb ? {
      host: cfg.host ?? 'localhost', port: cfg.port,
      database: cfg.database ?? '', user: cfg.user ?? '', password: cfg.password ?? '',
    } : connType === 'mongodb' ? { uri: cfg.uri ?? '', database: cfg.database ?? '' } : {}
    const load: Record<string, unknown> = isDb
      ? { table: cfg.table ?? '', mode: cfg.mode ?? 'replace' }
      : connType === 'mongodb' ? { collection: cfg.collection ?? '', mode: cfg.mode ?? 'replace' }
        : { table: cfg.path ?? '', mode: cfg.mode ?? 'replace' }
    destinations[key] = { type: connType, connection, load }
  }
  if (Object.keys(destinations).length === 0) {
    destinations['dest_main'] = { type: 'csv', connection: {}, load: { table: '', mode: 'replace' } }
    firstDestKey = 'dest_main'
  }

  return {
    name,
    sources,
    transformations: { steps },
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
    const tf   = YAML.load(yamls.transformations) as { transformations?: { steps: HdrStep[] } }
    const dst  = YAML.load(yamls.destinations) as { destinations?: Record<string, HdrDest> }
    type PipeShape = { name?: string; from: string; to: string; transformations?: string }
    const pip  = YAML.load(yamls.pipeline) as {
      pipeline?: PipeShape                                   // format canonique
      job?: { name?: string; pipeline?: PipeShape }          // ancien format imbriqué
    }

    const sources         = src?.sources ?? {}
    const transformations = tf?.transformations  ?? { steps: [] }
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

  // Sources
  const srcKeys = Object.keys(model.sources)
  for (const key of srcKeys) {
    const src = model.sources[key]
    const nodeType = CONNECTOR_TO_SOURCE_NODE[src.type] ?? 'source_csv'
    const id = `imported_src_${key}`
    const params: Record<string, unknown> = {
      ...src.connection,
      ...src.extract,
      path: (src.extract.table as string) ?? (src.connection as Record<string, unknown>).uri,
    }
    nodes.push({
      id, type: 'hydraNode', position: { x, y: 100 },
      data: { nodeType, label: key, params } as unknown as FlowNodeData,
    })
    x += 260
  }

  // Transformations
  const prevIds: string[] = srcKeys.map(k => `imported_src_${k}`)
  let lastTfId: string | null = null
  for (let i = 0; i < model.transformations.steps.length; i++) {
    const step = model.transformations.steps[i]
    const op   = Object.keys(step)[0]
    const nodeType = OP_TO_NODE[op] ?? 'transform_filter'
    const id = `imported_tf_${i}`
    nodes.push({
      id, type: 'hydraNode', position: { x, y: 100 },
      data: { nodeType, label: op, params: _stepToParams(op, step[op] as Record<string, unknown>) } as unknown as FlowNodeData,
    })
    const sourceId = lastTfId ?? prevIds[0]
    if (sourceId) edges.push({ id: `${sourceId}->${id}`, source: sourceId, target: id, animated: false })
    lastTfId = id
    x += 200
  }

  // Destinations
  const destKeys = Object.keys(model.destinations)
  for (const key of destKeys) {
    const dst = model.destinations[key]
    const nodeType = CONNECTOR_TO_DEST_NODE[dst.type] ?? 'dest_csv'
    const id = `imported_dst_${key}`
    const params: Record<string, unknown> = { ...dst.connection, ...dst.load }
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
