/**
 * ProjectSettings — onglet Settings › Project settings.
 *
 * Réglages du projet courant, écrits dans les fichiers du projet :
 * l'ordre d'exécution des workflows (workflows/thread.yaml) avec ses étapes,
 * délais, boucles et fallbacks (ThreadEditor : Define, Preview, Check).
 *
 * Projet courant : celui de l'URL (/settings/project/:projectId, ouvert par
 * le bouton « Project settings » de la page du projet) ; sinon le dernier
 * projet ouvert dans ce navigateur ; sinon on demande d'en choisir un.
 */
import { useEffect } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, FolderOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { forgetProject, lastProject, projectSettingsPath, rememberProject } from '@/lib/lastProject'
import ThreadEditor from '@/components/project/ThreadEditor'
import Spinner from '@/components/ui/Spinner'

/** Nom du fichier d'un workflow (workflows/<nom>.yaml), pour relier le schéma à l'éditeur. */
const fileName = (path: string | undefined, name: string) =>
  (path ?? '').replace(/\\/g, '/').split('/').pop()?.replace(/\.ya?ml$/i, '') || name

export default function ProjectSettings() {
  const { projectId } = useParams<{ projectId?: string }>()
  const navigate = useNavigate()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects.list })
  const project = useQuery({
    queryKey: ['project', projectId], queryFn: () => api.projects.get(projectId!), enabled: !!projectId,
  })
  const workflows = useQuery({
    queryKey: ['workflows', projectId], queryFn: () => api.workflows.list(projectId!), enabled: !!projectId,
  })

  useEffect(() => {
    if (project.data) rememberProject(project.data)
  }, [project.data])
  useEffect(() => {
    if (projectId && project.isError) forgetProject(projectId)
  }, [projectId, project.isError])

  // Arrivée par le menu : reprendre le dernier projet ouvert.
  if (!projectId) {
    const last = lastProject()
    if (last) return <Navigate to={projectSettingsPath(last.id)} replace />
  }

  const selector = (
    <select aria-label="Project" value={projectId ?? ''}
      onChange={e => e.target.value && navigate(projectSettingsPath(e.target.value))}
      style={{ background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8,
        padding: '6px 10px', color: 'var(--text-primary)', fontSize: 13 }}>
      <option value="">Choose a project…</option>
      {(projects.data ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  )

  if (!projectId) {
    return (
      <div className="card" style={{ maxWidth: 560 }} data-testid="project-settings-empty">
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>Project settings</h2>
        <p className="text-sm" style={{ color: 'var(--text-muted)', marginBottom: 14 }}>
          Settings of one project, written in its files. Open a project, or choose one:
        </p>
        <div className="flex items-center gap-3">
          {selector}
          <Link to="/overview" className="btn-secondary text-xs"><FolderOpen size={13} /> Projects</Link>
        </div>
      </div>
    )
  }

  if (project.isLoading) return <div className="flex justify-center py-10"><Spinner /></div>
  if (project.isError || !project.data) {
    return (
      <div className="card" style={{ maxWidth: 560 }}>
        <p className="text-sm" style={{ color: 'var(--error)', marginBottom: 12 }}>This project is not open in Studio.</p>
        {selector}
      </div>
    )
  }

  const p = project.data
  return (
    <div data-testid="project-settings">
      <div className="flex items-start gap-3 flex-wrap" style={{ marginBottom: 14 }}>
        <img src="/Hydra.png" alt="" style={{ width: 30, height: 30, objectFit: 'contain' }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 className="page-title" style={{ margin: 0 }}>{p.name}</h1>
          <p className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'monospace', margin: 0 }}>{p.path}</p>
          <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '2px 0 0' }}>
            Saved in the project files (workflows/thread.yaml), for everyone who opens the project.
          </p>
        </div>
        {selector}
        <Link to={`/projects/${p.id}`} className="btn-secondary text-xs">
          <ChevronLeft size={13} /> Back to the project
        </Link>
      </div>
      {workflows.isLoading
        ? <div className="flex justify-center py-10"><Spinner /></div>
        : (workflows.data?.length ?? 0) === 0
          ? <p className="text-sm" style={{ color: 'var(--text-muted)' }}>This project has no workflow yet.</p>
          : <ThreadEditor projectId={p.id} projectPath={p.path}
              workflowIds={Object.fromEntries((workflows.data ?? []).map(w => [fileName(w.path, w.name), w.id]))} />}
    </div>
  )
}
