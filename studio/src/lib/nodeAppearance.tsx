/**
 * nodeAppearance — couleur et icône d'un nœud, une seule source pour la palette
 * (menu de gauche) et le canvas (workflow et job) : un nœud déposé sur la scène
 * porte exactement la couleur et l'icône de son élément dans la palette.
 *
 *  - couleur : celle de la catégorie (Sources vert, Transformations indigo,
 *    Destinations orange, Actions cyan, Control Flow orange foncé, Jobs violet) ;
 *  - icône  : `icon` du nœud dans lib/nodeRegistry.ts.
 */
import {
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge, Rows3, ListOrdered, FileCode2, Database,
  Webhook, MessageSquare, Mail, Terminal, Network, Code, Variable, Equal, Server,
  GitBranch, LayoutGrid, Clock, Scissors, Link2,
  Package, Briefcase, FolderGit2, Snowflake, History,
} from 'lucide-react'
import { MySQLIcon, PostgreSQLIcon } from '@/components/icons/DatabaseIcons'
import { getNode, type NodeCategory } from '@/lib/nodeRegistry'

/** Nom d'icône (nodeRegistry.icon) → composant. */
export const NODE_ICONS: Record<string, React.ElementType> = {
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge, Rows3, ListOrdered, FileCode2, Database,
  Webhook, MessageSquare, Mail, Terminal, Network, Code, Variable, Equal, Server,
  GitBranch, LayoutGrid, Clock, Scissors, Link2,
  Package, FolderGit2,
  MySQL: MySQLIcon, PostgreSQL: PostgreSQLIcon, Snowflake, History,
  Briefcase,
}

export function resolveIcon(name: string | undefined): React.ElementType {
  return (name && NODE_ICONS[name]) || Briefcase
}

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  source:         'var(--success)',
  transformation: 'var(--primary)',
  destination:    'var(--warning)',
  action:         'var(--info)',
  control_flow:   '#f97316',
}

export const JOB_COLOR = '#8b5cf6'
/** Nœud Project (step type: project) : projet appelé par le workflow. */
export const PROJECT_COLOR = '#14b8a6'
export const CONTAINER_COLOR = '#f59e0b'
export const ERRORSCOPE_COLOR = '#ef4444'
export const RETRYSCOPE_COLOR = '#06b6d4'

/** Catégorie d'un type absent du registre (anciens types), d'après son préfixe. */
function categoryOf(nodeType: string): NodeCategory | null {
  if (nodeType.startsWith('source')) return 'source'
  if (nodeType.startsWith('dest')) return 'destination'
  if (nodeType.startsWith('transform')) return 'transformation'
  if (nodeType.startsWith('workflow_')) return 'control_flow'
  if (nodeType.startsWith('action')) return 'action'
  return null
}

export interface NodeAppearance { Icon: React.ElementType; color: string; category: NodeCategory | 'job' | 'project' | null }

export function nodeAppearance(nodeType: string | undefined): NodeAppearance {
  const t = nodeType ?? ''
  if (t === 'job') return { Icon: Package, color: JOB_COLOR, category: 'job' }
  if (t === 'project') return { Icon: FolderGit2, color: PROJECT_COLOR, category: 'project' }
  const def = getNode(t)
  const category = def?.category ?? categoryOf(t)
  return {
    Icon: resolveIcon(def?.icon),
    color: category ? CATEGORY_COLORS[category] : 'var(--primary)',
    category,
  }
}

/** Teinte transparente d'une couleur (fonctionne aussi avec var(--x)). */
export function tint(color: string, percent: number): string {
  return `color-mix(in srgb, ${color} ${percent}%, transparent)`
}
