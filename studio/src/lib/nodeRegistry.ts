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
  { type: 'source_csv',      label: 'CSV',        category: 'source', color: '#10b981', icon: 'FileSpreadsheet', description: 'Lit un fichier CSV',     maxInputs: 0 },
  { type: 'source_json',     label: 'JSON',       category: 'source', color: '#10b981', icon: 'Braces',          description: 'Lit un fichier JSON',    maxInputs: 0 },
  { type: 'source_parquet',  label: 'Parquet',    category: 'source', color: '#10b981', icon: 'Layers',          description: 'Lit un fichier Parquet', maxInputs: 0 },
  { type: 'source_mysql',    label: 'MySQL',      category: 'source', color: '#10b981', icon: 'MySQL',           description: 'Requête MySQL/MariaDB',  maxInputs: 0 },
  { type: 'source_postgres', label: 'PostgreSQL', category: 'source', color: '#10b981', icon: 'PostgreSQL',      description: 'Requête PostgreSQL',     maxInputs: 0 },
  { type: 'source_mongodb',  label: 'MongoDB',    category: 'source', color: '#10b981', icon: 'Container',       description: 'Collection MongoDB',     maxInputs: 0 },
  { type: 'source_api',      label: 'Web API',    category: 'source', color: '#10b981', icon: 'Globe',           description: 'Appel HTTP REST',        maxInputs: 0 },

  // Transformations
  { type: 'transform_filter',    label: 'Filter',      category: 'transformation', color: '#6366f1', icon: 'Filter',         description: 'Filtre les lignes sur condition' },
  { type: 'transform_select',    label: 'Select',      category: 'transformation', color: '#6366f1', icon: 'CheckSquare2',   description: 'Sélectionne des colonnes' },
  { type: 'transform_rename',    label: 'Rename',      category: 'transformation', color: '#6366f1', icon: 'Tags',           description: 'Renomme des colonnes' },
  { type: 'transform_cast',      label: 'Cast',        category: 'transformation', color: '#6366f1', icon: 'Binary',         description: 'Change le type de colonnes' },
  { type: 'transform_aggregate', label: 'Aggregate',   category: 'transformation', color: '#8b5cf6', icon: 'BarChart2',      description: 'Group by + agrégations' },
  { type: 'transform_sort',      label: 'Sort',        category: 'transformation', color: '#6366f1', icon: 'ArrowUpDown',    description: 'Trie les données' },
  { type: 'transform_dedupe',    label: 'Deduplicate', category: 'transformation', color: '#6366f1', icon: 'Fingerprint',    description: 'Supprime les doublons' },
  { type: 'transform_derive',    label: 'Derive',      category: 'transformation', color: '#8b5cf6', icon: 'FunctionSquare', description: 'Crée une colonne calculée' },
  { type: 'transform_join',      label: 'Join',        category: 'transformation', color: '#a78bfa', icon: 'GitMerge',       description: 'Joint deux flux sur une clé' },

  // Destinations
  { type: 'dest_csv',      label: 'CSV',        category: 'destination', color: '#f59e0b', icon: 'FileSpreadsheet', description: 'Écrit un fichier CSV',     maxOutputs: 0 },
  { type: 'dest_json',     label: 'JSON',       category: 'destination', color: '#f59e0b', icon: 'Braces',          description: 'Écrit un fichier JSON',    maxOutputs: 0 },
  { type: 'dest_parquet',  label: 'Parquet',    category: 'destination', color: '#f59e0b', icon: 'Layers',          description: 'Écrit un fichier Parquet', maxOutputs: 0 },
  { type: 'dest_mysql',    label: 'MySQL',      category: 'destination', color: '#f59e0b', icon: 'MySQL',           description: 'Insère dans MySQL',        maxOutputs: 0 },
  { type: 'dest_postgres', label: 'PostgreSQL', category: 'destination', color: '#f59e0b', icon: 'PostgreSQL',      description: 'Insère dans PostgreSQL',   maxOutputs: 0 },
  { type: 'dest_mongodb',  label: 'MongoDB',    category: 'destination', color: '#f59e0b', icon: 'Container',       description: 'Insère dans MongoDB',      maxOutputs: 0 },

  // Nœud Job (canvas workflow uniquement — ouvre le canvas job en double-clic)
  { type: 'job', label: 'Job', category: 'action', color: '#8b5cf6', icon: 'Package',
    description: 'Sous-pipeline ETL (source → transform → dest)', maxInputs: -1, maxOutputs: -1 },

  // Actions workflow
  { type: 'action_webhook',    label: 'Webhook',    category: 'action', color: '#06b6d4', icon: 'Webhook',  description: 'Appel HTTP sortant' },
  { type: 'action_email',      label: 'Email',      category: 'action', color: '#06b6d4', icon: 'Mail',     description: 'Envoi d\'email' },

  // Actions système (shell + script)
  { type: 'action_bash',       label: 'Bash',       category: 'action', color: '#16a34a', icon: 'Terminal', description: 'Exécute un script Bash (Linux / macOS)', platform: 'unix' },
  { type: 'action_powershell', label: 'PowerShell', category: 'action', color: '#2563eb', icon: 'Terminal', description: 'Exécute un script PowerShell (Windows)', platform: 'windows' },
  { type: 'action_python',     label: 'Python',     category: 'action', color: '#eab308', icon: 'FileCode2', description: 'Exécute un script Python' },
  { type: 'action_ssh',        label: 'SSH',        category: 'action', color: '#0ea5e9', icon: 'Server',   description: 'Exécute une commande SSH distante' },

  // Flux de contrôle (canvas workflow uniquement)
  { type: 'cf_condition', label: 'Condition', category: 'control_flow', color: '#f97316', icon: 'GitFork',    description: 'Branch if / else sur condition' },
  { type: 'cf_parallel',  label: 'Parallel',  category: 'control_flow', color: '#f97316', icon: 'Layers',     description: 'Exécution parallèle explicite' },
  { type: 'cf_delay',     label: 'Delay',     category: 'control_flow', color: '#f97316', icon: 'Clock',      description: 'Attente temporisée' },
  { type: 'cf_split',     label: 'Split',     category: 'control_flow', color: '#f97316', icon: 'Split',      description: '1 flux → N branches' },
  { type: 'cf_merge',     label: 'Merge',     category: 'control_flow', color: '#f97316', icon: 'GitMerge',   description: 'N flux → 1 flux (par clé)' },
  { type: 'cf_join',      label: 'Join',      category: 'control_flow', color: '#f97316', icon: 'Link',       description: 'N flux → 1 flux (clé commune)' },
]

NODES.forEach(def => registerNode(def))

