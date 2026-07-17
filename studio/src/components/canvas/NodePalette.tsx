/**
 * NodePalette — panneau latéral gauche du canvas.
 * L'utilisateur glisse un type de nœud sur le canvas pour l'ajouter.
 *
 * Modes :
 *  - Expanded (w-52) : icône + label + catégories collapsibles
 *  - Collapsed (w-12) : icônes seules, draggables, tooltip au hover
 *
 * sceneMode :
 *  - 'jobs'     → Sources · Transformations · Destinations · Actions
 *  - 'workflow' → Actions · Control Flow · Jobs (liste dynamique)
 *  - undefined  → tout
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { getNodesByCategory, NodeCategory, HydraNodeDef } from '@/lib/nodeRegistry'
import {
  ChevronDown, ChevronRight, ChevronLeft,
  // Catégories
  HardDriveDownload, Shuffle, HardDriveUpload, Zap, GitBranch,
  // Sources
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  // Transformations
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge,
  // Actions
  Webhook, MessageSquare, Mail, Terminal, Network, Code,
  // Control Flow
  LayoutGrid, Clock, Scissors, Link2,
  // Job node
  Package,
  // Container
  Boxes, ShieldAlert, RotateCcw,
  // Fallback
  Briefcase,
} from 'lucide-react'
import { MySQLIcon, PostgreSQLIcon } from '@/components/icons/DatabaseIcons'

// ── Icône string → composant Lucide ───────────────────────────────────────────

const LUCIDE: Record<string, React.ElementType> = {
  // Sources
  FileSpreadsheet, Braces, Layers, Cylinder, Container, Globe,
  // Transformations
  Filter, CheckSquare2, Tags, Binary, BarChart2, ArrowUpDown,
  Fingerprint, FunctionSquare, GitMerge,
  // Actions
  Webhook, MessageSquare, Mail, Terminal, Network, Code,
  // Control Flow
  GitBranch, LayoutGrid, Clock, Scissors, Link2,
  // Job
  Package,
  // Databases custom
  MySQL: MySQLIcon, PostgreSQL: PostgreSQLIcon,
  // Fallback
  Briefcase,
}

function resolveIcon(name: string): React.ElementType {
  return LUCIDE[name] ?? Briefcase
}

// ── Catégories registry ───────────────────────────────────────────────────────

const CATEGORIES: { id: NodeCategory; label: string; icon: React.ElementType }[] = [
  { id: 'source',         label: 'Sources',        icon: HardDriveDownload },
  { id: 'transformation', label: 'Transformations', icon: Shuffle },
  { id: 'destination',    label: 'Destinations',   icon: HardDriveUpload },
  { id: 'action',         label: 'Actions',        icon: Zap },
  { id: 'control_flow',   label: 'Control Flow',   icon: GitBranch },
]

const CATEGORY_COLORS: Record<NodeCategory, string> = {
  source:         'var(--success)',
  transformation: 'var(--primary)',
  destination:    'var(--warning)',
  action:         'var(--info)',
  control_flow:   '#f97316',
}

const JOB_COLOR = '#8b5cf6'
const CONTAINER_COLOR = '#f59e0b'
const ERRORSCOPE_COLOR = '#ef4444'
const RETRYSCOPE_COLOR = '#06b6d4'

const PALETTE_KEY = 'hydra-palette-collapsed'

// ── Props ─────────────────────────────────────────────────────────────────────

export interface JobEntry { id: string; name: string }

interface Props {
  onDragStart: (event: React.DragEvent, nodeType: string) => void
  onJobDragStart?: (event: React.DragEvent, jobId: string) => void
  onJobContextMenu?: (event: React.MouseEvent, jobId: string) => void
  replaceMode?: boolean
  onCancelReplace?: () => void
  /** 'jobs'     → Sources/Transformations/Destinations/Actions
   *  'workflow' → Actions/ControlFlow/Jobs(dynamic)
   *  undefined  → tout */
  sceneMode?: 'jobs' | 'workflow'
  /** Liste des jobs définis — affichés dans la section Jobs (sceneMode === 'workflow') */
  jobsList?: JobEntry[]
}

// ── Composant ─────────────────────────────────────────────────────────────────

export default function NodePalette({
  onDragStart, onJobDragStart, onJobContextMenu, replaceMode, onCancelReplace, sceneMode, jobsList = [],
}: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({
    source: true,
    transformation: false,
    destination: true,
    action: false,
    control_flow: false,
    containers: true,
    jobs: true,
  })

  // Plateforme backend — détermine quels nœuds système sont disponibles
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'],
    queryFn: api.system.info,
    staleTime: Infinity,
  })
  const isWindows = sysInfo?.is_windows ?? false
  const isUnix    = sysInfo ? !sysInfo.is_windows : false

  // Filtrer les catégories selon la scène
  const visibleCategories = sceneMode === 'workflow'
    ? CATEGORIES.filter(c => c.id === 'action' || c.id === 'control_flow')
    : sceneMode === 'jobs'
      ? CATEGORIES.filter(c => c.id === 'source' || c.id === 'transformation' || c.id === 'destination' || c.id === 'action')
      : CATEGORIES

  function isPlatformAvailable(node: HydraNodeDef): boolean {
    if (!node.platform) return true
    if (node.platform === 'windows') return isWindows
    if (node.platform === 'unix')    return isUnix
    return true
  }

  function platformBadge(node: HydraNodeDef): string | null {
    if (node.platform === 'windows') return 'Win'
    if (node.platform === 'unix')    return 'Unix'
    return null
  }

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem(PALETTE_KEY) === 'true' } catch { return false }
  })

  const toggleCollapse = () => setCollapsed(v => {
    const next = !v
    try { localStorage.setItem(PALETTE_KEY, String(next)) } catch {}
    return next
  })

  // ── Mode collapsed ────────────────────────────────────────────────────────

  if (collapsed) {
    return (
      <div
        className="shrink-0 flex flex-col overflow-y-auto"
        style={{
          width: 48,
          background:  'var(--bg-card)',
          borderRight: '1px solid var(--bg-border)',
          boxShadow:   '8px 0 10px -4px rgba(0,0,0,0.45)',
          position:    'relative',
          zIndex:      10,
        }}
      >
        {/* Header — bouton expand */}
        <div
          className="flex items-center justify-center h-10"
          style={{ borderBottom: '1px solid var(--bg-border)' }}
        >
          <button
            onClick={toggleCollapse}
            title="Expand palette"
            className="btn-ghost !px-1.5 !py-1.5 !gap-0"
            style={{ color: 'var(--text-muted)' }}
          >
            <ChevronLeft size={14} className="rotate-180" />
          </button>
        </div>

        {/* Icônes des nœuds registry */}
        <div className="flex flex-col py-1 gap-0.5 px-1">
          {visibleCategories.map(cat => {
            const nodes = getNodesByCategory(cat.id)
            const color = CATEGORY_COLORS[cat.id]
            return (
              <div key={cat.id}>
                <div style={{ height: 2, borderRadius: 1, background: `${color}40`, margin: '4px 4px 3px' }} />
                {nodes.map(node => (
                  <CollapsedNodeItem key={node.type} node={node} color={color} onDragStart={onDragStart} />
                ))}
              </div>
            )
          })}

          {/* Containers (collapsed) */}
          <div>
            <div style={{ height: 2, borderRadius: 1, background: `${CONTAINER_COLOR}40`, margin: '4px 4px 3px' }} />
            <div
              draggable
              onDragStart={e => onDragStart(e, 'container')}
              title="Sequence Container"
              style={{
                width: 40, height: 40, borderRadius: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'grab', margin: '0 auto 3px', transition: 'opacity 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.7' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1' }}
            >
              <Boxes size={22} style={{ color: CONTAINER_COLOR }} />
            </div>
          </div>

          {/* Jobs (collapsed) — sceneMode workflow */}
          {sceneMode === 'workflow' && jobsList.length > 0 && (
            <div>
              <div style={{ height: 2, borderRadius: 1, background: `${JOB_COLOR}40`, margin: '4px 4px 3px' }} />
              {jobsList.map(job => (
                <div
                  key={job.id}
                  draggable
                  onDragStart={e => onJobDragStart?.(e, job.id)}
                  title={job.name}
                  style={{
                    width: 40, height: 40, borderRadius: 10,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    cursor: 'grab', margin: '0 auto 3px', transition: 'opacity 0.15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.7' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1' }}
                >
                  <Package size={22} style={{ color: JOB_COLOR }} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  // ── Mode expanded ─────────────────────────────────────────────────────────

  return (
    <div
      className="w-52 shrink-0 flex flex-col overflow-y-auto"
      style={{
        background:  'var(--bg-card)',
        borderRight: '1px solid var(--bg-border)',
        boxShadow:   '8px 0 10px -4px rgba(0,0,0,0.45)',
        position:    'relative',
        zIndex:      10,
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 h-10"
        style={{ borderBottom: '1px solid var(--bg-border)' }}
      >
        <p className="text-xs font-semibold" style={{ color: replaceMode ? 'var(--primary)' : 'var(--text-muted)' }}>
          {replaceMode ? '↓ CHOOSE REPLACEMENT' : 'NODE PALETTE'}
        </p>
        <div className="flex items-center gap-1">
          {replaceMode && (
            <button
              onClick={onCancelReplace}
              className="text-xs hover:opacity-70 transition-opacity"
              style={{ color: 'var(--text-muted)' }}
            >
              Cancel
            </button>
          )}
          <button
            onClick={toggleCollapse}
            title="Collapse palette"
            className="btn-ghost !px-1 !py-1 !gap-0"
            style={{ color: 'var(--text-muted)' }}
          >
            <ChevronLeft size={13} />
          </button>
        </div>
      </div>

      {/* Catégories registry */}
      {visibleCategories.map(cat => {
        const nodes  = getNodesByCategory(cat.id)
        // Exclure le nœud générique 'job' de la catégorie 'action' en mode workflow
        // (les jobs apparaissent dans la section dynamique ci-dessous)
        const filteredNodes = (sceneMode === 'workflow' && cat.id === 'action')
          ? nodes.filter(n => n.type !== 'job')
          : nodes
        const isOpen = open[cat.id] ?? false
        const color  = CATEGORY_COLORS[cat.id]
        const CatIcon = cat.icon

        return (
          <div key={cat.id}>
            <button
              onClick={() => setOpen(o => ({ ...o, [cat.id]: !o[cat.id] }))}
              className="w-full flex items-center justify-between px-3 py-2 transition-opacity hover:opacity-70"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="flex items-center gap-1.5">
                <CatIcon size={26} style={{ color, flexShrink: 0 }} />
                <span className="text-xs font-medium">{cat.label}</span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>({filteredNodes.length})</span>
              </div>
              {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>

            {isOpen && (
              <div className="pb-1">
                {filteredNodes.map(node => {
                  const Icon      = resolveIcon(node.icon)
                  const available = isPlatformAvailable(node)
                  const badge     = platformBadge(node)
                  return (
                    <div
                      key={node.type}
                      draggable={available}
                      onDragStart={e => available ? onDragStart(e, node.type) : e.preventDefault()}
                      className="flex items-center gap-2 mx-2 mb-0.5 px-2 py-2 rounded-lg transition-opacity"
                      style={{
                        cursor:     available ? 'grab' : 'not-allowed',
                        opacity:    available ? 1 : 0.4,
                      }}
                      title={available ? node.description : `${node.description} — non disponible sur cette plateforme`}
                    >
                      <div style={{
                        width: 32, height: 32, borderRadius: 8,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <Icon size={18} style={{ color }} />
                      </div>
                      <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                        {node.label}
                      </span>
                      {badge && (
                        <span style={{
                          fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
                          padding: '1px 5px', borderRadius: 4,
                          background: available ? `${color}30` : 'var(--bg-hover)',
                          color: available ? color : 'var(--text-muted)',
                          flexShrink: 0,
                        }}>{badge}</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {/* ── Section Containers (les deux scènes) ─────────────────────────── */}
      <div>
        <button
          onClick={() => setOpen(o => ({ ...o, containers: !o.containers }))}
          className="w-full flex items-center justify-between px-3 py-2 transition-opacity hover:opacity-70"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="flex items-center gap-1.5">
            <Boxes size={26} style={{ color: CONTAINER_COLOR, flexShrink: 0 }} />
            <span className="text-xs font-medium">Containers</span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>(3)</span>
          </div>
          {open.containers ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>

        {open.containers && (
          <div className="pb-1">
            <div
              draggable
              onDragStart={e => onDragStart(e, 'container')}
              className="flex items-center gap-2 mx-2 mb-0.5 px-2 py-2 rounded-lg"
              style={{
                cursor: 'grab',
              }}
              title="Glisser pour regrouper des nœuds — repliable pour gagner de la place"
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Boxes size={18} style={{ color: CONTAINER_COLOR }} />
              </div>
              <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                Sequence Container
              </span>
            </div>

            <div
              draggable
              onDragStart={e => onDragStart(e, 'container:errorscope')}
              className="flex items-center gap-2 mx-2 mb-0.5 px-2 py-2 rounded-lg"
              style={{
                cursor: 'grab',
              }}
              title="Politique d'erreur (on_failure) appliquée à tout le bloc"
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <ShieldAlert size={18} style={{ color: ERRORSCOPE_COLOR }} />
              </div>
              <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                Error Scope
              </span>
            </div>

            <div
              draggable
              onDragStart={e => onDragStart(e, 'container:retryscope')}
              className="flex items-center gap-2 mx-2 mb-0.5 px-2 py-2 rounded-lg"
              style={{
                cursor: 'grab',
              }}
              title="Re-tentatives (retry) appliquées à tout le bloc"
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <RotateCcw size={18} style={{ color: RETRYSCOPE_COLOR }} />
              </div>
              <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                Retry Scope
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── Section Jobs dynamique (sceneMode === 'workflow') ──────────────── */}
      {sceneMode === 'workflow' && (
        <div>
          <button
            onClick={() => setOpen(o => ({ ...o, jobs: !o.jobs }))}
            className="w-full flex items-center justify-between px-3 py-2 transition-opacity hover:opacity-70"
            style={{ color: 'var(--text-secondary)' }}
          >
            <div className="flex items-center gap-1.5">
              <Package size={26} style={{ color: JOB_COLOR, flexShrink: 0 }} />
              <span className="text-xs font-medium">Jobs</span>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>({jobsList.length})</span>
            </div>
            {open.jobs ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>

          {open.jobs && (
            <div className="pb-1">
              {jobsList.length === 0 ? (
                <p className="text-xs mx-3 mb-2 italic" style={{ color: 'var(--text-muted)' }}>
                  Aucun job défini — créez-en dans l'onglet Jobs configuration.
                </p>
              ) : jobsList.map(job => (
                <div
                  key={job.id}
                  draggable
                  onDragStart={e => onJobDragStart?.(e, job.id)}
                  onContextMenu={e => { e.preventDefault(); onJobContextMenu?.(e, job.id) }}
                  className="flex items-center gap-2 mx-2 mb-0.5 px-2 py-2 rounded-lg"
                  style={{
                    cursor: 'grab',
                  }}
                  title={`Glisser pour ajouter "${job.name}" — clic droit pour les options`}
                >
                  <div style={{
                    width: 32, height: 32, borderRadius: 8,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <Package size={18} style={{ color: JOB_COLOR }} />
                  </div>
                  <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                    {job.name}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── CollapsedNodeItem ─────────────────────────────────────────────────────────

function CollapsedNodeItem({
  node, color, onDragStart,
}: {
  node: HydraNodeDef
  color: string
  onDragStart: (e: React.DragEvent, type: string) => void
}) {
  const Icon = resolveIcon(node.icon)
  return (
    <div
      draggable
      onDragStart={e => onDragStart(e, node.type)}
      title={node.label}
      style={{
        width: 40, height: 40, borderRadius: 10,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'grab', margin: '0 auto 3px', transition: 'opacity 0.15s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.7' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1' }}
    >
      <Icon size={22} style={{ color }} />
    </div>
  )
}
