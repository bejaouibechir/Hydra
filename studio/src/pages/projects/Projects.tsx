import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, Project } from '@/lib/api'
import { Plus, FolderOpen, Trash2, ArrowRight, Calendar, FolderSearch } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import Modal from '@/components/ui/Modal'
import { pickPath } from '@/components/ui/FolderPicker'
import { Link, useNavigate } from 'react-router-dom'

function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [name,       setName]       = useState('')
  const [desc,       setDesc]       = useState('')
  const [projPath,   setProjPath]   = useState('')
  const [browsing,   setBrowsing]   = useState(false)

  const { data: sysInfo } = useQuery({ queryKey: ['system-info'], queryFn: api.system.info, staleTime: Infinity })

  const mut = useMutation({
    mutationFn: () => api.projects.create({
      name,
      description: desc || undefined,
      project_path: projPath.trim() || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      onClose()
      setName(''); setDesc(''); setProjPath('')
    },
  })

  const browse = async () => {
    setBrowsing(true)
    try {
      const res = await pickPath('directory')
      if (res.path) setProjPath(res.path)
    } finally { setBrowsing(false) }
  }

  return (
    <Modal title="New Project" open={open} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!name.trim() || mut.isPending}>
          {mut.isPending ? 'Creating…' : 'Create Project'}
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
          <input className="input" placeholder="Optional description" value={desc} onChange={e => setDesc(e.target.value)} />
        </div>

        {/* Répertoire du projet */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            Parent folder
            <span className="ml-1 font-normal" style={{ color: 'var(--text-muted)' }}>
              (optional — e.g. D:\Projects → creates D:\Projects\my-project)
            </span>
          </label>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              className="input"
              placeholder="Leave empty to use the default workspace"
              value={projPath}
              onChange={e => setProjPath(e.target.value)}
              style={{ flex: 1 }}
            />
            <button
              onClick={browse}
              disabled={browsing}
              title="Choose a folder"
              style={{
                padding: '0 12px', borderRadius: 8, flexShrink: 0,
                background: 'var(--bg-hover)', border: '1px solid var(--bg-border)',
                color: 'var(--text-secondary)', cursor: browsing ? 'wait' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
              }}
            >
              <FolderSearch size={14} />
              {browsing ? '…' : 'Browse'}
            </button>
          </div>
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
            Automatically creates: <code>jobs/</code>, <code>data/input/</code>, <code>data/output/</code>
          </p>
        </div>

        {mut.isError && <p className="text-xs" style={{ color: 'var(--error)' }}>{(mut.error as Error).message}</p>}
      </div>
    </Modal>
  )
}

function ProjectCard({ project }: { project: Project }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const workflows = useQuery({
    queryKey: ['workflows', project.id],
    queryFn: () => api.workflows.list(project.id),
  })
  const del = useMutation({
    mutationFn: () => api.projects.delete(project.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate('/projects')
    },
  })

  return (
    <div className="card hover:opacity-90 transition-opacity group"
      style={{ borderColor: 'var(--bg-border)' }}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: 'var(--primary-subtle)' }}>
            <FolderOpen size={16} style={{ color: 'var(--primary)' }} />
          </div>
          <div>
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{project.name}</h3>
            {project.description && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{project.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/projects/${project.id}`} className="btn-primary text-xs flex items-center gap-1.5 py-1">
            Open <ArrowRight size={12} />
          </Link>
          <button
            onClick={() => { if (confirm('Delete "' + project.name + '"?')) del.mutate() }}
            disabled={del.isPending}
            className="btn-secondary text-xs flex items-center gap-1 py-1"
            style={{ color: 'var(--error)' }}
          ><Trash2 size={12} /></button>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-muted)' }}>
        <span className="flex items-center gap-1"><Calendar size={11} />{new Date(project.created_at).toLocaleDateString()}</span>
        {workflows.data && <span>{workflows.data.length} workflow{workflows.data.length !== 1 ? 's' : ''}</span>}
        {project.path && <span className="font-mono truncate max-w-48" title={project.path}>{project.path}</span>}
      </div>
    </div>
  )
}

export default function Projects() {
  const [createOpen, setCreateOpen] = useState(false)
  const projectsQ = useQuery({ queryKey: ['projects'], queryFn: api.projects.list })
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Projects</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>Manage your Hydra ETL projects</p>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> New Project
        </button>
      </div>
      {projectsQ.isPending && <div className="flex justify-center py-16"><Spinner /></div>}
      {projectsQ.isError && <div className="text-sm py-8 text-center" style={{ color: 'var(--error)' }}>{(projectsQ.error as Error).message}</div>}
      {projectsQ.data?.length === 0 && (
        <EmptyState
          icon={<FolderOpen size={40} style={{ color: 'var(--text-muted)' }} />}
          title="No projects"
          description="Create your first project to get started."
          action={<button className="btn-primary flex items-center gap-2" onClick={() => setCreateOpen(true)}><Plus size={16} /> New Project</button>}
        />
      )}
      {projectsQ.data && projectsQ.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projectsQ.data.map(p => <ProjectCard key={p.id} project={p} />)}
        </div>
      )}
      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
