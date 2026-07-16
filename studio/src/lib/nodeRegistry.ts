/**
 * nodeRegistry.ts — Centralise la définition de tous les types de nœuds Hydra.
 */

export type NodeCategory = 'source' | 'transformation' | 'destination' | 'action' | 'control_flow'

export interface HydraNodeDef {
  type: string
  label: string
  category: NodeCategory
  description: string
  color: string
  icon: string
  defaultData?: Record<string, unknown>
  maxInputs?: number
  maxOutputs?: number
  platform?: 'unix' | 'windows'
}

// ── Registry ──────────────────────────────────────────────────────────────────

const _registry = new Map<string, HydraNodeDef>()

export function registerNode(def: HydraNodeDef): void {
  _registry.set(def.type, def)
}

export function getNode(type: string): HydraNodeDef | undefined {
  return _registry.get(type)
}

export function getAllNodes(): HydraNodeDef[] {
  return Array.from(_registry.values())
}

export function getNodesByCategory(category: NodeCategory): HydraNodeDef[] {
  return Array.from(_registry.values()).filter(n => n.category === category)
}

// ── Nœuds ─────────────────────────────────────────────────────────────────────

const NODES: HydraNodeDef[] = [
  // Sources
  { type: 'source_csv',      label: 'CSV',        category: 'source', color: '#10b981', icon: 'FileSpreadsheet', description: 'Reads a CSV file',     maxInputs: 0 },
  { type: 'source_json',     label: 'JSON',       category: 'source', color: '#10b981', icon: 'Braces',          description: 'Reads a JSON file',    maxInputs: 0 },
  { type: 'source_parquet',  label: 'Parquet',    category: 'source', color: '#10b981', icon: 'Layers',          description: 'Reads a Parquet file', maxInputs: 0 },
  { type: 'source_mysql',    label: 'MySQL',      category: 'source', color: '#10b981', icon: 'MySQL',           description: 'MySQL/MariaDB query',  maxInputs: 0 },
  { type: 'source_postgres', label: 'PostgreSQL', category: 'source', color: '#10b981', icon: 'PostgreSQL',      description: 'PostgreSQL query',     maxInputs: 0 },
  { type: 'source_mongodb',  label: 'MongoDB',    category: 'source', color: '#10b981', icon: 'Container',       description: 'MongoDB collection',     maxInputs: 0 },
  { type: 'source_api',      label: 'Web API',    category: 'source', color: '#10b981', icon: 'Globe',           description: 'REST HTTP call',        maxInputs: 0 },

  // Transformations
  { type: 'transform_filter',    label: 'Filter',      category: 'transformation', color: '#6366f1', icon: 'Filter',         description: 'Filters rows by condition' },
  { type: 'transform_select',    label: 'Select',      category: 'transformation', color: '#6366f1', icon: 'CheckSquare2',   description: 'Selects columns' },
  { type: 'transform_rename',    label: 'Rename',      category: 'transformation', color: '#6366f1', icon: 'Tags',           description: 'Renames columns' },
  { type: 'transform_cast',      label: 'Cast',        category: 'transformation', color: '#6366f1', icon: 'Binary',         description: 'Changes column types' },
  { type: 'transform_aggregate', label: 'Aggregate',   category: 'transformation', color: '#8b5cf6', icon: 'BarChart2',      description: 'Group by + aggregations' },
  { type: 'transform_sort',      label: 'Sort',        category: 'transformation', color: '#6366f1', icon: 'ArrowUpDown',    description: 'Sorts the data' },
  { type: 'transform_dedupe',    label: 'Deduplicate', category: 'transformation', color: '#6366f1', icon: 'Fingerprint',    description: 'Removes duplicates' },
  { type: 'transform_derive',    label: 'Derive',      category: 'transformation', color: '#8b5cf6', icon: 'FunctionSquare', description: 'Creates a computed column' },
  { type: 'transform_join',      label: 'Join',        category: 'transformation', color: '#a78bfa', icon: 'GitMerge',       description: 'Joins two flows on a key' },
  { type: 'transform_fill_null', label: 'Fill Null',   category: 'transformation', color: '#6366f1', icon: 'Binary',         description: 'Replaces null values' },
  { type: 'transform_trim',      label: 'Trim',        category: 'transformation', color: '#6366f1', icon: 'Scissors',       description: 'Removes extra spaces' },
  { type: 'transform_clean',     label: 'Clean',       category: 'transformation', color: '#6366f1', icon: 'Tags',           description: 'Cleans text (spaces, case)' },
  { type: 'transform_pivot',     label: 'Pivot',       category: 'transformation', color: '#8b5cf6', icon: 'LayoutGrid',     description: 'Long to wide (pivot)' },
  { type: 'transform_unpivot',   label: 'Unpivot',     category: 'transformation', color: '#8b5cf6', icon: 'Layers',         description: 'Wide to long (melt)' },
  { type: 'transform_transpose', label: 'Transpose',   category: 'transformation', color: '#8b5cf6', icon: 'ArrowUpDown',     description: 'Swap rows and columns' },
  { type: 'transform_merge',     label: 'Merge',       category: 'transformation', color: '#a78bfa', icon: 'Link2',          description: 'Upsert a source into a target (SQL MERGE)' },
  { type: 'transform_union',     label: 'Union',       category: 'transformation', color: '#a78bfa', icon: 'Layers',         description: 'Append a source (UNION / UNION ALL)' },
  { type: 'transform_script',    label: 'Script',      category: 'transformation', color: '#8b5cf6', icon: 'FileCode2',      description: 'Custom Python transformation (input -> output columns)' },

  // Destinations
  { type: 'dest_csv',      label: 'CSV',        category: 'destination', color: '#f59e0b', icon: 'FileSpreadsheet', description: 'Writes a CSV file',     maxOutputs: 0 },
  { type: 'dest_json',     label: 'JSON',       category: 'destination', color: '#f59e0b', icon: 'Braces',          description: 'Writes a JSON file',    maxOutputs: 0 },
  { type: 'dest_parquet',  label: 'Parquet',    category: 'destination', color: '#f59e0b', icon: 'Layers',          description: 'Writes a Parquet file', maxOutputs: 0 },
  { type: 'dest_mysql',    label: 'MySQL',      category: 'destination', color: '#f59e0b', icon: 'MySQL',           description: 'Inserts into MySQL',        maxOutputs: 0 },
  { type: 'dest_postgres', label: 'PostgreSQL', category: 'destination', color: '#f59e0b', icon: 'PostgreSQL',      description: 'Inserts into PostgreSQL',   maxOutputs: 0 },
  { type: 'dest_mongodb',  label: 'MongoDB',    category: 'destination', color: '#f59e0b', icon: 'Container',       description: 'Inserts into MongoDB',      maxOutputs: 0 },

  // Nœud Job (canvas workflow uniquement — ouvre le canvas job en double-clic)
  { type: 'job', label: 'Job', category: 'action', color: '#8b5cf6', icon: 'Package',
    description: 'ETL sub-pipeline (source → transform → dest)', maxInputs: -1, maxOutputs: -1 },

  // Actions workflow
  { type: 'action_webhook',    label: 'Webhook',    category: 'action', color: '#06b6d4', icon: 'Webhook',  description: 'Outgoing HTTP call' },
  { type: 'action_email',      label: 'Email',      category: 'action', color: '#06b6d4', icon: 'Mail',     description: 'Send email' },

  // Actions système (shell + script)
  { type: 'action_bash',       label: 'Bash',       category: 'action', color: '#16a34a', icon: 'Terminal', description: 'Runs a Bash script (Linux / macOS)', platform: 'unix' },
  { type: 'action_powershell', label: 'PowerShell', category: 'action', color: '#2563eb', icon: 'Terminal', description: 'Runs a PowerShell script (Windows)', platform: 'windows' },
  { type: 'action_python',     label: 'Python',     category: 'action', color: '#eab308', icon: 'FileCode2', description: 'Runs a Python script' },
  { type: 'action_ssh',        label: 'SSH',        category: 'action', color: '#0ea5e9', icon: 'Server',   description: 'Runs a remote SSH command' },

  // Flux de contrôle (canvas workflow uniquement)
  { type: 'cf_condition', label: 'Condition', category: 'control_flow', color: '#f97316', icon: 'GitFork',    description: 'Branch if / else on condition' },
  { type: 'cf_parallel',  label: 'Parallel',  category: 'control_flow', color: '#f97316', icon: 'Layers',     description: 'Explicit parallel execution' },
  { type: 'cf_delay',     label: 'Delay',     category: 'control_flow', color: '#f97316', icon: 'Clock',      description: 'Timed wait' },
  { type: 'cf_split',     label: 'Split',     category: 'control_flow', color: '#f97316', icon: 'Split',      description: '1 flow → N branches' },
  { type: 'cf_merge',     label: 'Merge',     category: 'control_flow', color: '#f97316', icon: 'GitMerge',   description: 'N flows → 1 flow (by key)' },
  { type: 'cf_join',      label: 'Join',      category: 'control_flow', color: '#f97316', icon: 'Link',       description: 'N flows → 1 flow (common key)' },
]

NODES.forEach(def => registerNode(def))

