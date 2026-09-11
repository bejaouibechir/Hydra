import { useState, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Workflow } from '@/lib/api'
import { Plus, GitBranch, Trash2, ArrowRight, ChevronLeft, Upload, Clock, Webhook } from 'lucide-react'
import StatusBadge from '@/components/ui/StatusBadge'
import { useRunsList } from '@/hooks/useRunPolling'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import Modal from '@/components/ui/Modal'
import * as yaml from 'js-yaml'
import { sectionYamlsToJobModel, jobModelToFlow, type JobSectionYamls } from '@/lib/hdrSerializer'
import { buildWorkflowLayout, type ImportStep } from '@/lib/workflowImport'

function CreateWorkflowModal({ projectId, open, onClose }: { projectId: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState<'manual' | 'schedule' | 'webhook'>('manual')
  const [cron, setCron] = useState('0 8 * * *')

  const mut = useMutation({
    mutationFn: () => api.workflows.create({
      name, project_id: projectId, trigger_type: trigger,
      cron: trigger === 'schedule' ? cron : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflows', projectId] }); onClose(); setName('') },
  })

  return (
    <Modal title="New Workflow" open={open} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={() => mut.mutate()} disabled={!name.trim() || mut.isPending}>
          {mut.isPending ? 'Creating…' : 'Create Workflow'}
        </button>
      </>}>
      <div className="space-y-3">
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            Workflow name <span style={{ color: 'var(--error)' }}>*</span>
          </label>
          <input className="input" placeholder="daily_sync" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Trigger</label>
          <select className="input" value={trigger} onChange={e => setTrigger(e.target.value as typeof trigger)}>
            <option value="manual">Manual</option>
            <option value="schedule">Schedule (cron)</option>
            <option value="webhook">Webhook</option>
          </select>
        </div>
        {trigger === 'schedule' && (
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Cron expression</label>
            <input className="input font-mono" placeholder="0 8 * * *" value={cron} onChange={e => setCron(e.target.value)} />
          </div>
        )}
        {mut.isError && <p className="text-xs" style={{ color: 'var(--error)' }}>{(mut.error as Error).message}</p>}
      </div>
    </Modal>
  )
}

function TriggerEditor({ wf, projectId }: { wf: Workflow; projectId: string }) {
  const qc = useQueryClient()
  const [type, setType] = useState<'manual' | 'schedule' | 'webhook'>(
    (wf.trigger_type as 'manual' | 'schedule' | 'webhook') ?? 'manual')
  const [cron, setCron] = useState(wf.cron ?? '0 8 * * *')

  const mut = useMutation({
    mutationFn: (patch: { trigger_type: string; cron?: string }) =>
      api.workflows.update(wf.id, projectId, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflows', projectId] }),
  })
  const apply = (t: string, c: string) =>
    mut.mutate({ trigger_type: t, cron: t === 'schedule' ? c : undefined })

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <label className="text-xs shrink-0" style={{ color: 'var(--text-secondary)' }}>Trigger</label>
        <select
          className="input !py-1 text-xs flex-1"
          value={type}
          onChange={e => { const t = e.target.value as typeof type; setType(t); apply(t, cron) }}
        >
          <option value="manual">Manual</option>
          <option value="schedule">Schedule (cron)</option>
          <option value="webhook">Webhook</option>
        </select>
        {mut.isPending && <Spinner size="sm" />}
      </div>
      {type === 'schedule' && (
        <>
          <input
            className="input !py-1 text-xs font-mono"
            value={cron}
            placeholder="0 8 * * *"
            onChange={e => setCron(e.target.value)}
            onBlur={() => apply('schedule', cron)}
            onKeyDown={e => { if (e.key === 'Enter') apply('schedule', cron) }}
          />
          <a
            href="http://127.0.0.1:5678/api/workflows/scheduled/list"
            target="_blank"
            rel="noreferrer"
            className="text-xs"
            style={{ color: 'var(--text-muted)', textDecoration: 'none' }}
            title="Opens the list of scheduled jobs with their next run time"
          >
            Next run time → /api/workflows/scheduled/list
          </a>
        </>
      )}
      {mut.isError && (
        <span className="text-xs" style={{ color: 'var(--error)' }}>{(mut.error as Error).message}</span>
      )}
    </div>
  )
}


export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const importRef = useRef<HTMLInputElement>(null)

  const importMut = useMutation({
    mutationFn: async (files: File[]) => {
      // 1. Trouver workflow.yaml à la racine du dossier sélectionné
      const EXPECTED_YAMLS = ['sources.yaml', 'transformations.yaml', 'destinations.yaml', 'pipeline.yaml']
      const wfFile = files.find(f => {
        const rel = (f as any).webkitRelativePath ?? f.name
        const parts = rel.split('/')
        return parts.length === 2 && parts[1].toLowerCase() === 'workflow.yaml'
      })
      if (!wfFile) throw new Error('workflow.yaml was not found at the root of the selected folder.')

      const wfText = await wfFile.text()
      const parsed = yaml.load(wfText) as any
      const wfObj = parsed?.workflow ?? parsed

      const name: string = wfObj?.name ?? 'imported_workflow'
      const trigger_type: string = wfObj?.trigger?.type ?? 'manual'
      const cron: string | undefined = wfObj?.trigger?.cron
      const steps: any[] = wfObj?.steps ?? []

      // Préfixe du dossier racine (ex: "workflow_sales_analytics/")
      const rootPrefix = ((wfFile as any).webkitRelativePath ?? wfFile.name).split('/')[0] + '/'

      // 2. Index de tous les fichiers par chemin relatif (lowercase)
      const fileIndex = new Map<string, File>()
      for (const f of files) {
        const rel = ((f as any).webkitRelativePath ?? f.name) as string
        fileIndex.set(rel.toLowerCase(), f)
      }

      // 3. Layout du canvas workflow — TOUS les steps, jobs et actions.
      //    La construction est isolée dans lib/workflowImport.ts pour être
      //    testable seule.
      const {
        nodes: wfNodes,
        edges: wfEdges,
        stepNameToJobId,
        jobNames: jobNamesMap,
      } = buildWorkflowLayout(steps as ImportStep[])

      const jobCanvases: Record<string, { nodes: any[]; edges: any[] }> = {}

      // Parser les YAML de chaque job
      for (const step of steps) {
        if (step.type !== 'job' || !step.job) continue
        const jobId = stepNameToJobId.get(step.name)!

        // Résoudre le dossier du job depuis le chemin relatif (ex: "./jobs/01_extract_orders/pipeline.yaml")
        const cleanPath = (step.job as string).replace(/^\.\//, '')
        const pathParts = cleanPath.split('/')
        const jobFolderRel = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') + '/' : ''
        const jobFolderPrefix = (rootPrefix + jobFolderRel).toLowerCase()

        // Trouver les 4 YAML dans ce dossier
        const yamlFiles: Record<string, File> = {}
        for (const [relLower, f] of fileIndex) {
          if (relLower.startsWith(jobFolderPrefix)) {
            const fname = relLower.split('/').pop()!
            if (EXPECTED_YAMLS.includes(fname)) yamlFiles[fname] = f
          }
        }

        const hasMissing = EXPECTED_YAMLS.some(n => !yamlFiles[n])
        if (hasMissing) { jobCanvases[jobId] = { nodes: [], edges: [] }; continue }

        try {
          const [sources, transformations, destinations, pipeline] = await Promise.all(
            EXPECTED_YAMLS.map(n => yamlFiles[n].text())
          )
          const yamls: JobSectionYamls = { sources, transformations, destinations, pipeline }
          const model = sectionYamlsToJobModel(yamls, step.name)
          if (model) {
            const { nodes: jNodes, edges: jEdges } = jobModelToFlow(model)
            jobCanvases[jobId] = { nodes: jNodes, edges: jEdges }
          } else {
            jobCanvases[jobId] = { nodes: [], edges: [] }
          }
        } catch { jobCanvases[jobId] = { nodes: [], edges: [] } }
      }


      // 5. Créer le workflow via API
      const created = await api.workflows.create({
        name,
        project_id: projectId,
        trigger_type: trigger_type as 'manual' | 'schedule' | 'webhook',
        cron: trigger_type === 'schedule' ? cron : undefined,
      })

      // 6. Sauvegarder le layout complet + yaml_content
      await api.workflows.update(created.id, projectId!, {
        layout: {
          nodes: wfNodes,
          edges: wfEdges,
          job_canvases: jobCanvases,
          job_names: jobNamesMap,
        },
        yaml_content: wfText,
      } as any)

      return created
    },
    onSuccess: (wf) => {
      qc.invalidateQueries({ queryKey: ['workflows', projectId] })
      navigate(`/workflows/${wf.id}?projectId=${projectId}`)
    },
    onError: (e: Error) => setImportError(e.message),
  })

  const handleImportFolder = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setImportError(null)
    importMut.mutate(files)
  }

  const project   = useQuery({ queryKey: ['project', projectId],   queryFn: () => api.projects.get(projectId!) })
  const workflows = useQuery({ queryKey: ['workflows', projectId], queryFn: () => api.workflows.list(projectId!) })

  const delWf = useMutation({
    mutationFn: (wfId: string) => api.workflows.delete(wfId, projectId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workflows', projectId] }),
  })

  // ── Runs : dernier statut affiché sur chaque carte (information passive) ──
  const runs = useRunsList()

  /** Dernier run d'un workflow — matche le nom Studio OU le nom du fichier yaml */
  const lastRunFor = (wf: Workflow) => {
    const stem = (wf.path ?? '').replace(/\\/g, '/').split('/').pop()?.replace(/\.ya?ml$/i, '')
    return (runs.data ?? []).find(r => r.workflow_name === wf.name || r.workflow_name === stem)
  }

  const fmtAgo = (iso: string) => {
    const s = (Date.now() - new Date(iso).getTime()) / 1000
    if (s < 60) return 'just now'
    if (s < 3600) return `${Math.floor(s / 60)} min ago`
    if (s < 86400) return `${Math.floor(s / 3600)} hr ago`
    return `${Math.floor(s / 86400)} days ago`
  }

  if (project.isLoading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  if (!project.data) return <p style={{ color: 'var(--error)' }}>Project not found.</p>

  const TriggerIcon = ({ t }: { t: string }) =>
    t === 'schedule' ? <Clock size={16} style={{ color: '#8b5cf6' }} />
    : t === 'webhook' ? <Webhook size={16} style={{ color: '#8b5cf6' }} />
    : <GitBranch size={16} style={{ color: '#8b5cf6' }} />

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
        <Link to="/overview" className="flex items-center gap-1 hover:opacity-70 transition-opacity">
          <ChevronLeft size={14} /> Overview
        </Link>
        <span>/</span>
        <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{project.data.name}</span>
      </div>

      <div className="page-header">
        <div>
          <div className="flex items-center gap-3">
            <img src="/Hydra.png" alt="" style={{ width: 30, height: 30, objectFit: 'contain' }} />
            <div>
              <h1 className="page-title" style={{ margin: 0 }}>{project.data.name}</h1>
              <p className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'monospace', margin: 0 }}>
                {project.data.path}
              </p>
              <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '2px 0 0' }}>
                {workflows.data?.length ?? 0} workflow{(workflows.data?.length ?? 0) > 1 ? 's' : ''}
              </p>
            </div>
          </div>
          {project.data.description && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{project.data.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Import Workflow depuis un dossier (webkitdirectory) */}
          <input
            ref={importRef}
            type="file"
            onChange={handleImportFolder}
            style={{ display: 'none' }}
            // @ts-expect-error webkitdirectory non standard
            webkitdirectory=""
            mozdirectory=""
          />
          <button className="btn-secondary" onClick={() => importRef.current?.click()} disabled={importMut.isPending}>
            <Upload size={15} /> {importMut.isPending ? 'Importing…' : 'Import workflow'}
          </button>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={16} /> New workflow
          </button>
        </div>
        {importError && (
          <p className="text-xs mt-1 text-right" style={{ color: 'var(--error)' }}>{importError}</p>
        )}
      </div>

      {workflows.isLoading
        ? <div className="flex justify-center py-20"><Spinner size="lg" /></div>
        : workflows.data?.length === 0
          ? <EmptyState icon={GitBranch} title="No workflows"
              description="Create your first workflow to start building ETL pipelines."
              action={<button className="btn-primary" onClick={() => setShowCreate(true)}><Plus size={16} /> New workflow</button>} />
          : <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 16 }}>
              {workflows.data?.map(wf => {
                const lastRun  = lastRunFor(wf)
                const jobCount = wf.layout?.job_names
                  ? Object.keys(wf.layout.job_names as Record<string, unknown>).length
                  : null
                return (
                <div key={wf.id} className="card group"
                  style={{ display: 'flex', flexDirection: 'column', gap: 12, transition: 'border-color 0.15s', width: 270 }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--primary)')}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--bg-border)')}>

                  {/* En-tête : icône trigger + nom + suppression */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2.5" style={{ minWidth: 0 }}>
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                        style={{ background: 'rgba(139,92,246,0.12)' }}>
                        <TriggerIcon t={wf.trigger_type} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <h3 className="font-semibold text-sm truncate" style={{ color: 'var(--text-primary)' }}>{wf.name}</h3>
                        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          <span className="capitalize">{wf.trigger_type}</span>
                          {wf.cron && <span className="font-mono"> · {wf.cron}</span>}
                          {jobCount != null && <span> · {jobCount} job{jobCount > 1 ? 's' : ''}</span>}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete workflow “${wf.name}”?\nThe workflow.yaml file will be deleted; jobs will remain unchanged.`))
                          delWf.mutate(wf.id)
                      }}
                      title="Delete workflow"
                      className="btn-ghost p-1.5 !gap-0 opacity-0 group-hover:opacity-100"
                      style={{ color: 'var(--error)' }}>
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {/* Statut + dernier run */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <StatusBadge status={wf.published ? 'published' : 'draft'} />
                    {lastRun ? (
                      <Link to={`/runs/${lastRun.run_id}`} className="flex items-center gap-1.5"
                        style={{ textDecoration: 'none' }} title="View latest run">
                        <StatusBadge status={lastRun.status} />
                        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          {fmtAgo(lastRun.started_at)}
                        </span>
                      </Link>
                    ) : (
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>never run</span>
                    )}
                  </div>

                  {/* Trigger — modifiable après création */}
                  <TriggerEditor wf={wf} projectId={projectId!} />

                  {/* Action : éditeur */}
                  <Link to={`/workflows/${wf.id}?projectId=${projectId}`}
                    className="btn-secondary w-full justify-between text-xs !py-1.5" style={{ marginTop: 'auto' }}>
                    Open in editor <ArrowRight size={13} />
                  </Link>
                </div>
              )})}
            </div>}

      <CreateWorkflowModal projectId={projectId!} open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
