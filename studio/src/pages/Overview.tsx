/**
 * Overview — Page d'accueil style Visual Studio Start Page
 * Projets récents, pins favoris, actions rapides, stats
 */
import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api, Project } from '@/lib/api'
import {
  FolderOpen, Star, Search, Plus, GitBranch, Play, CheckCircle2,
  Clock, ArrowRight, FolderSearch, Zap, Activity, MoreHorizontal,
  Trash2, ExternalLink, ChevronRight, AlertTriangle,
} from 'lucide-react'
import { useNotifications } from '@/contexts/NotificationContext'
import Spinner from '@/components/ui/Spinner'
import Modal from '@/components/ui/Modal'
import { pickPath } from '@/components/ui/FolderPicker'
import StatusBadge from '@/components/ui/StatusBadge'
import { useRunsList } from '@/hooks/useRunPolling'

// ── Persistance locale ────────────────────────────────────────────────────────
const PINS_KEY      = 'hydra_pinned_project_ids'
const RECENTS_KEY   = 'hydra_recent_project_ids'  // liste ordonnée des IDs ouverts
const MAX_RECENTS   = 20

function getPins(): string[] {
  try { return JSON.parse(localStorage.getItem(PINS_KEY)   ?? '[]') } catch { return [] }
}
function getRecents(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENTS_KEY) ?? '[]') } catch { return [] }
}
function savePins(ids: string[])    { localStorage.setItem(PINS_KEY,    JSON.stringify(ids)) }
function recordOpen(id: string) {
  const prev = getRecents().filter(r => r !== id)
  localStorage.setItem(RECENTS_KEY, JSON.stringify([id, ...prev].slice(0, MAX_RECENTS)))
}

// ── Sous-composants ───────────────────────────────────────────────────────────

function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [name,     setName]     = useState('')
  const [desc,     setDesc]     = useState('')
  const [projPath, setProjPath] = useState('')
  const [browsing, setBrowsing] = useState(false)

  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'], queryFn: api.system.info, staleTime: Infinity,
  })

  const mut = useMutation({
    mutationFn: () => api.projects.create({
      name, description: desc || undefined,
      project_path: projPath.trim() || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      onClose(); setName(''); setDesc(''); setProjPath('')
    },
  })

  const browse = async () => {
    setBrowsing(true)
    try { const r = await pickPath('directory'); if (r.path) setProjPath(r.path) }
    finally { setBrowsing(false) }
  }

  return (
    <Modal title="New project" open={open} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!name.trim() || mut.isPending}>
          {mut.isPending ? 'Creating…' : 'Create project'}
        </button>
      </>}>
      <div className="space-y-3">
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            Project name <span style={{ color: 'var(--error)' }}>*</span>
          </label>
          <input className="input" placeholder="my-etl-project" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && name.trim() && mut.mutate()} />
        </div>
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Description</label>
          <input className="input" placeholder="Optional description" value={desc}
            onChange={e => setDesc(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            Parent folder
            <span className="ml-1 font-normal" style={{ color: 'var(--text-muted)' }}>
              (optional)
            </span>
          </label>
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="input" placeholder="Leave empty to use the default workspace"
              value={projPath} onChange={e => setProjPath(e.target.value)} style={{ flex: 1 }} />
            <button onClick={browse} disabled={browsing} style={{
              padding: '0 12px', borderRadius: 8, flexShrink: 0,
              background: 'var(--bg-hover)', border: '1px solid var(--bg-border)',
              color: 'var(--text-secondary)', cursor: browsing ? 'wait' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
            }}>
              <FolderSearch size={14} />{browsing ? '…' : 'Browse'}
            </button>
          </div>
        </div>
        {mut.isError && <p className="text-xs" style={{ color: 'var(--error)' }}>{(mut.error as Error).message}</p>}
      </div>
    </Modal>
  )
}

// Ligne de projet dans la liste
function ProjectRow({
  project, pinned, onTogglePin, onOpen, onDelete,
}: {
  project: Project
  pinned: boolean
  onTogglePin: () => void
  onOpen: () => void
  onDelete: () => void
}) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 12px', borderRadius: 8, cursor: 'pointer',
        background: hovered ? 'var(--bg-hover)' : 'transparent',
        transition: 'background 0.1s',
        borderLeft: pinned ? '2px solid var(--primary)' : '2px solid transparent',
      }}
    >
      {/* Pin toggle */}
      <button
        onClick={e => { e.stopPropagation(); onTogglePin() }}
        title={pinned ? 'Unpin' : 'Pin'}
        style={{
          background: 'none', border: 'none', cursor: 'pointer', padding: 2,
          color: pinned ? 'var(--warning)' : 'var(--text-muted)',
          opacity: hovered || pinned ? 1 : 0,
          transition: 'opacity 0.15s, color 0.15s',
          flexShrink: 0,
        }}
      >
        <Star size={14} fill={pinned ? 'currentColor' : 'none'} />
      </button>

      {/* Icône Hydra */}
      <div style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--primary-subtle)',
      }}>
        <img src="/Hydra.png" alt="" style={{ width: 20, height: 20, objectFit: 'contain' }} />
      </div>

      {/* Infos */}
      <Link
        to={`/projects/${project.id}`}
        onClick={onOpen}
        style={{ flex: 1, textDecoration: 'none', minWidth: 0 }}
      >
        <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {project.name}
        </div>
        {project.path && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 1 }}>
            {project.path}
          </div>
        )}
      </Link>

      {/* Date */}
      <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0, marginLeft: 8 }}>
        {new Date(project.created_at).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: '2-digit' })}
      </span>

      {/* Supprimer */}
      <button
        onClick={e => { e.stopPropagation(); onDelete() }}
        title="Delete project (folder and shortcut)"
        style={{
          background: 'none', border: 'none', cursor: 'pointer', padding: 3,
          color: 'var(--text-muted)', flexShrink: 0, borderRadius: 6,
          opacity: hovered ? 1 : 0, transition: 'opacity 0.15s, color 0.15s',
          display: 'flex', alignItems: 'center',
        }}
        onMouseEnter={e => (e.currentTarget.style.color = 'var(--error)')}
        onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
      >
        <Trash2 size={13} />
      </button>

      {/* Arrow */}
      <ChevronRight size={13} style={{ color: 'var(--text-muted)', flexShrink: 0, opacity: hovered ? 1 : 0, transition: 'opacity 0.15s' }} />
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
      color: 'var(--text-muted)', textTransform: 'uppercase',
      padding: '8px 12px 4px',
    }}>
      {children}
    </div>
  )
}

// Carte d'action « Démarrer » — style Visual Studio Start Window
function StartAction({
  icon: Icon, title, desc, onClick, disabled, primary,
}: {
  icon: React.ComponentType<{ size?: number | string; style?: React.CSSProperties }>
  title: string
  desc: string
  onClick?: () => void
  disabled?: boolean
  primary?: boolean
}) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 12, width: '100%',
        padding: '12px 14px', borderRadius: 10, textAlign: 'left',
        background: hovered && !disabled ? 'var(--bg-hover)' : 'var(--bg-main)',
        border: primary ? '1px solid var(--primary)' : '1px solid var(--bg-border)',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        transition: 'background 0.12s, border-color 0.12s',
      }}
    >
      <div style={{
        width: 34, height: 34, borderRadius: 8, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--primary-subtle)',
      }}>
        <Icon size={16} style={{ color: 'var(--primary)' }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</div>
        <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.4 }}>{desc}</div>
      </div>
    </button>
  )
}

function fmtDuration(s?: number) {
  if (!s) return '—'
  return s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`
}

// ── Composant principal ───────────────────────────────────────────────────────

export default function Overview() {
  const [pins,       setPinsState]   = useState<string[]>(getPins)
  const [recents,    setRecents]     = useState<string[]>(getRecents)
  const [search,     setSearch]      = useState('')
  const [showCreate, setShowCreate]  = useState(false)
  const [opening,    setOpening]     = useState(false)
  // Message d'erreur d'ouverture (dossier non-projet, backend indisponible…)
  const [openError,  setOpenError]   = useState<string | null>(null)
  const navigate = useNavigate()
  const { add: notify } = useNotifications()

  const projectsQ = useQuery({ queryKey: ['projects'], queryFn: api.projects.list, refetchInterval: 15_000 })
  const runs      = useRunsList()

  // Mettre à jour les recents depuis localStorage à chaque focus
  useEffect(() => {
    const onFocus = () => setRecents(getRecents())
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  const togglePin = useCallback((id: string) => {
    setPinsState(prev => {
      const next = prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
      savePins(next)
      return next
    })
  }, [])

  const handleOpen = useCallback((id: string) => {
    recordOpen(id)
    setRecents(getRecents())
  }, [])

  const qc = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [deleting,     setDeleting]     = useState(false)

  /** Suppression — removeFiles=false : raccourci seul (endpoint /unlist,
   *  incapable de toucher au disk) ; true : DELETE destructeur assumé */
  const confirmDelete = useCallback(async (p: Project, removeFiles: boolean) => {
    setDeleting(true)
    try {
      if (removeFiles) await api.projects.delete(p.id)
      else             await api.projects.unlist(p.id)
    } catch (err) {
      alert(`Unable to delete:\n${err instanceof Error ? err.message : String(err)}`)
      setDeleting(false)
      return
    }
    const nextPins = getPins().filter(id => id !== p.id)
    savePins(nextPins)
    setPinsState(nextPins)
    localStorage.setItem(RECENTS_KEY, JSON.stringify(getRecents().filter(id => id !== p.id)))
    setRecents(getRecents())
    qc.invalidateQueries({ queryKey: ['projects'] })
    setDeleting(false)
    setDeleteTarget(null)
  }, [qc])

  /** Ouvre un projet : sélecteur de dossier dans les 2 cas.
   *  adopt=false → « Ouvrir un projet » : exige un projet Hydra existant
   *  adopt=true  → « Ouvrir un dossier local » : adopte n'importe quel dossier */
  const openFromDisk = useCallback(async (adopt: boolean) => {
    setOpening(true)
    setOpenError(null)
    try {
      const r = await pickPath('directory')
      if (!r.path) return                       // dialogue annulé
      const proj = await api.projects.open(r.path, adopt)
      recordOpen(proj.id)
      navigate(`/projects/${proj.id}`)
    } catch (err) {
      // Mauvais choix de dossier → notification + bannière, on reste sur l'accueil
      const msg = err instanceof Error ? err.message : String(err)
      setOpenError(msg)
      notify('warning', 'Unable to open this folder', msg)
    } finally {
      setOpening(false)
    }
  }, [navigate, notify])

  // Filtrage + tri
  const allProjects = projectsQ.data ?? []
  const filtered    = search
    ? allProjects.filter(p => p.name.toLowerCase().includes(search.toLowerCase()) || (p.path ?? '').toLowerCase().includes(search.toLowerCase()))
    : allProjects

  // Pinned en haut, puis recents (ordre d'ouverture), puis le reste par date desc
  const pinnedProjects = filtered.filter(p => pins.includes(p.id))
  const nonPinned      = filtered.filter(p => !pins.includes(p.id))

  const recentIds = recents.filter(id => nonPinned.some(p => p.id === id))
  const recentProjects  = recentIds.map(id => nonPinned.find(p => p.id === id)!).filter(Boolean)
  const otherProjects   = nonPinned.filter(p => !recentIds.includes(p.id))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  // Stats
  const activeRuns    = (runs.data ?? []).filter(r => r.status === 'running').length
  const recentRunList = (runs.data ?? []).slice(0, 5)
  const successRate   = runs.data?.length
    ? Math.round((runs.data.filter(r => r.status === 'success').length / runs.data.length) * 100)
    : null

  const hasProjects = allProjects.length > 0

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 28 }}>
        <img src="/Hydra.png" alt="Hydra" style={{ width: 42, height: 42, objectFit: 'contain' }} />
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>
            Hydra Studio
          </h1>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
            Data platform — ETL Engine · Feature Engine · Intelligence Engine
          </p>
        </div>
      </div>

      {/* ── Alerte ouverture : dossier non-projet ── */}
      {openError && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 10,
          padding: '10px 14px', borderRadius: 10, marginBottom: 16,
          background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.35)',
        }}>
          <AlertTriangle size={15} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--warning)' }}>
              This folder is not a Hydra project
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.45 }}>
              {openError}
            </div>
          </div>
          <button onClick={() => setOpenError(null)} title="Close"
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, padding: 2 }}>
            ✕
          </button>
        </div>
      )}

      {/* ── Main layout ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20, alignItems: 'start' }}>

        {/* ── Colonne gauche : liste des projets ── */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>

          {/* Barre de recherche */}
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--bg-border)' }}>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{
                position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--text-muted)', pointerEvents: 'none',
              }} />
              <input
                className="input"
                placeholder="Search projects…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ paddingLeft: 30, height: 32, fontSize: 12 }}
              />
            </div>
          </div>

          {projectsQ.isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : !hasProjects ? (
            <div style={{ textAlign: 'center', padding: '48px 24px' }}>
              <FolderOpen size={40} style={{ color: 'var(--text-muted)', marginBottom: 12, opacity: 0.4 }} />
              <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
                No projects yet
              </p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
                Create your first project to start building ETL pipelines.
              </p>
              <button className="btn-primary" onClick={() => setShowCreate(true)}>
                <Plus size={15} /> New project
              </button>
            </div>
          ) : (
            <div style={{ padding: '4px 0 8px' }}>

              {/* Épinglés */}
              {pinnedProjects.length > 0 && (
                <>
                  <SectionLabel>⭐ Pinned</SectionLabel>
                  {pinnedProjects.map(p => (
                    <ProjectRow key={p.id} project={p} pinned
                      onTogglePin={() => togglePin(p.id)}
                      onOpen={() => handleOpen(p.id)}
                      onDelete={() => setDeleteTarget(p)} />
                  ))}
                </>
              )}

              {/* Récents */}
              {recentProjects.length > 0 && (
                <>
                  <SectionLabel>🕐 Recently opened</SectionLabel>
                  {recentProjects.map(p => (
                    <ProjectRow key={p.id} project={p} pinned={false}
                      onTogglePin={() => togglePin(p.id)}
                      onOpen={() => handleOpen(p.id)}
                      onDelete={() => setDeleteTarget(p)} />
                  ))}
                </>
              )}

              {/* Tous les autres */}
              {otherProjects.length > 0 && (
                <>
                  {(recentProjects.length > 0 || pinnedProjects.length > 0) && (
                    <SectionLabel>All projects</SectionLabel>
                  )}
                  {otherProjects.map(p => (
                    <ProjectRow key={p.id} project={p} pinned={false}
                      onTogglePin={() => togglePin(p.id)}
                      onOpen={() => handleOpen(p.id)}
                      onDelete={() => setDeleteTarget(p)} />
                  ))}
                </>
              )}

              {/* Aucun résultat */}
              {filtered.length === 0 && (
                <p style={{ textAlign: 'center', padding: '24px 0', fontSize: 12, color: 'var(--text-muted)' }}>
                  No project matches “{search}”
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Colonne droite : actions + stats ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Actions rapides */}
          <div className="card" style={{ padding: 16 }}>
            <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>
              Get started
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <StartAction icon={GitBranch} title="Clone a repository"
                desc="Get a project from an online repository such as GitHub or Azure DevOps — coming soon"
                disabled />
              <StartAction icon={FolderOpen} title="Open a project"
                desc="Select an existing Hydra project folder — workflows and jobs load automatically"
                onClick={() => openFromDisk(false)} disabled={opening} />
              <StartAction icon={Plus} title="Create a project" primary
                desc="Create a project with generated data, output, jobs, and workflows folders"
                onClick={() => setShowCreate(true)} />
            </div>

            <div style={{ height: 1, background: 'var(--bg-border)', margin: '14px 0' }} />

            <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>
              Links
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {[
                { label: 'Documentation', href: 'https://hydraetl.com' },
                { label: 'GitHub', href: 'https://github.com/hydraetl' },
              ].map(({ label, href }) => (
                <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--primary)', textDecoration: 'none', padding: '3px 0' }}>
                  <ExternalLink size={11} /> {label}
                </a>
              ))}
            </div>
          </div>

          {/* Stats */}
          <div className="card" style={{ padding: 16 }}>
            <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>
              Statistics
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { label: 'Projects', value: allProjects.length, icon: FolderOpen, color: 'var(--primary)' },
                { label: 'Active runs', value: activeRuns, icon: Activity, color: 'var(--success)' },
                { label: 'Success rate', value: successRate !== null ? `${successRate}%` : '—', icon: CheckCircle2, color: 'var(--warning)' },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <Icon size={12} style={{ color }} />
                    {label}
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Runs récents */}
          {recentRunList.length > 0 && (
            <div className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', margin: 0 }}>
                  Recent runs
                </p>
                <Link to="/runs" style={{ fontSize: 10, color: 'var(--primary)', textDecoration: 'none' }}>View all →</Link>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {recentRunList.map(run => (
                  <Link key={run.run_id} to={`/runs/${run.run_id}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', padding: '4px 0' }}>
                    <StatusBadge status={run.status} />
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {run.workflow_name}
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace', flexShrink: 0 }}>
                      {run.status === 'running' ? '…' : fmtDuration(run.duration)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <CreateProjectModal open={showCreate} onClose={() => setShowCreate(false)} />

      {/* ── Modal suppression : raccourci seul OU raccourci + dossier ── */}
      <Modal title="Delete project" open={deleteTarget != null} onClose={() => setDeleteTarget(null)}
        footer={<>
          <button className="btn-secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
            Cancel
          </button>
          <button className="btn-secondary" disabled={deleting}
            onClick={() => deleteTarget && confirmDelete(deleteTarget, false)}>
            Remove from list
          </button>
          <button className="btn-primary" disabled={deleting}
            style={{ background: 'var(--error)', borderColor: 'var(--error)' }}
            onClick={() => deleteTarget && confirmDelete(deleteTarget, true)}>
            {deleting ? 'Deleting…' : 'Delete folder too'}
          </button>
        </>}>
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
          “{deleteTarget?.name}”
        </p>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 4 }}>
          {deleteTarget?.path}
        </p>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 12, lineHeight: 1.5 }}>
          <strong>Remove from list</strong> — removes the shortcut and keeps the folder unchanged on disk.<br />
          <strong>Delete folder too</strong> — permanently deletes the project folder and all of its contents.
        </p>
      </Modal>
    </div>
  )
}
