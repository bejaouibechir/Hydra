/**
 * ProjectStepDialog — configuration d'un nœud Project (step type: project).
 *
 * Le workflow lance un autre projet. Rien ne passe implicitement sauf
 * l'environnement : les paramètres (params) et variables (variables) sont
 * donnés ici ; le projet appelé garde ses propres secrets. Chaque changement
 * est vérifié par l'API (POST /projects/{id}/project-step) : projet introuvable,
 * cycle (a → b → a), profondeur ; l'enregistrement est refusé tant qu'il y a
 * une erreur.
 */
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Plus, ExternalLink, AlertTriangle, FolderGit2, Loader2 } from 'lucide-react'
import { api, type Project } from '@/lib/api'
import type { FlowNodeData, ProjectStepConfig } from '@/lib/workflowSerializer'
import { PROJECT_COLOR } from '@/lib/nodeAppearance'

interface Props {
  masterProjectId: string
  masterPath?: string
  data: FlowNodeData
  projects: Project[]
  onSave: (patch: Partial<FlowNodeData>) => void
  onClose: () => void
}

interface Row { id: number; key: string; value: string }
let _seq = 1
const rowsOf = (m?: Record<string, unknown>): Row[] =>
  Object.entries(m ?? {}).map(([key, v]) => ({ id: _seq++, key, value: v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v) }))
const mapOf = (rows: Row[]) => Object.fromEntries(rows.filter(r => r.key.trim() && r.value !== '').map(r => [r.key.trim(), r.value]))

export default function ProjectStepDialog({ masterProjectId, data, projects, onSave, onClose }: Props) {
  const init = (data.projectStep ?? { project: '' }) as ProjectStepConfig
  const [stepName, setStepName] = useState(String(data.stepName ?? ''))
  const [project, setProject] = useState(init.project ?? '')
  const [ref, setRef] = useState<'path' | 'name'>(init.ref ?? 'path')
  const [env, setEnv] = useState(init.env ?? 'inherit')
  const [workflows, setWorkflows] = useState<string[]>(init.workflows ?? [])
  const [outputs, setOutputs] = useState((init.outputs ?? []).join(', '))
  const [isolation, setIsolation] = useState(init.isolation ?? 'inprocess')
  const [timeout, setTimeoutV] = useState(init.timeout != null ? String(init.timeout) : '')
  const [overlap, setOverlap] = useState(init.overlap ?? 'wait')
  const [onFailure, setOnFailure] = useState(String(data.onFailure ?? 'fail'))
  const [params, setParams] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries((data.params ?? {}) as Record<string, unknown>).map(([k, v]) => [k, v == null ? '' : String(v)])))
  const [extraParams, setExtraParams] = useState<Row[]>([])
  const [variables, setVariables] = useState<Row[]>(rowsOf(init.variables))

  // Vérification par l'API (debounce léger via la clé de requête)
  const [checked, setChecked] = useState({ project, ref, workflows })
  useEffect(() => {
    const t = setTimeout(() => setChecked({ project, ref, workflows }), 350)
    return () => clearTimeout(t)
  }, [project, ref, workflows])
  const info = useQuery({
    queryKey: ['project-step', masterProjectId, checked],
    queryFn: () => api.projects.projectStep(masterProjectId, { project: checked.project, ref: checked.ref, workflows: checked.workflows }),
    enabled: Boolean(checked.project.trim()),
  })
  const names = useQuery({ queryKey: ['env-names', masterProjectId], queryFn: () => api.globalEnv.names(masterProjectId) })

  const decls = info.data?.parameters ?? {}
  const declNames = Object.keys(decls)
  // Paramètres connus du step mais non déclarés par le projet appelé : lignes libres
  useEffect(() => {
    if (!info.data) return
    setExtraParams(rows => rows.length ? rows : rowsOf(Object.fromEntries(
      Object.entries(params).filter(([k]) => !(k in (info.data?.parameters ?? {}))))))
  }, [info.data])                                     // eslint-disable-line react-hooks/exhaustive-deps

  const envChoices = useMemo(() => Array.from(new Set([
    ...(names.data ?? []).map(n => n.name), ...(info.data?.environments ?? []),
  ])).sort(), [names.data, info.data])

  const missingRequired = declNames.filter(n => {
    const d = decls[n] ?? {}
    return d.required && (d.default === undefined || d.default === null) && !(params[n] ?? '').trim()
  })
  const errors = [
    ...(!project.trim() ? ['Choose the project to run.'] : []),
    ...(info.data?.errors ?? []),
    ...(!stepName.trim() ? ['The step needs a name.'] : []),
  ]
  const canSave = errors.length === 0 && !info.isFetching && Boolean(info.data?.ok)

  const choose = (p: Project) => {
    if (ref === 'name') setProject(p.name)
    else setProject(p.path)                          // l'API renvoie le chemin relatif → normalisé à l'enregistrement
  }

  const save = () => {
    const rel = ref === 'path' ? (info.data?.relative ?? project) : project
    const cfg: ProjectStepConfig = {
      project: rel, ref, env,
      workflows: workflows.length ? workflows : undefined,
      outputs: outputs.split(',').map(s => s.trim()).filter(Boolean),
      variables: mapOf(variables),
      isolation: isolation as ProjectStepConfig['isolation'],
      timeout: timeout.trim() || undefined,
      overlap: overlap as ProjectStepConfig['overlap'],
      displayName: info.data?.name ?? undefined,
    }
    const p: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(params)) if (k in decls && v.trim() !== '') p[k] = v
    Object.assign(p, mapOf(extraParams))
    onSave({ stepName: stepName.trim(), label: info.data?.name ?? 'Project', projectStep: cfg, params: p,
             onFailure: onFailure as FlowNodeData['onFailure'] })
  }

  const input: React.CSSProperties = { boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }
  const label: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', margin: '12px 0 4px', display: 'block' }
  const hint: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }
  const kvRows = (rows: Row[], set: (r: Row[]) => void, ph: [string, string], test: string) => (
    <div data-testid={test}>
      {rows.map(r => (
        <div key={r.id} style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
          <input style={{ ...input, width: 170, fontFamily: 'monospace' }} value={r.key} placeholder={ph[0]}
            onChange={e => set(rows.map(x => x.id === r.id ? { ...x, key: e.target.value } : x))} />
          <input style={{ ...input, flex: 1 }} value={r.value} placeholder={ph[1]}
            onChange={e => set(rows.map(x => x.id === r.id ? { ...x, value: e.target.value } : x))} />
          <button type="button" onClick={() => set(rows.filter(x => x.id !== r.id))}
            style={{ border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', borderRadius: 6, color: 'var(--text-muted)', cursor: 'pointer' }}><X size={12} /></button>
        </div>
      ))}
      <button type="button" className="btn-secondary text-xs" onClick={() => set([...rows, { id: _seq++, key: '', value: '' }])}>
        <Plus size={12} /> Add
      </button>
    </div>
  )

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} data-testid="project-step-dialog"
        style={{ width: 640, maxHeight: '88vh', overflow: 'auto', background: 'var(--bg-card)', borderRadius: 12,
          border: `1px solid ${PROJECT_COLOR}`, padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <FolderGit2 size={18} style={{ color: PROJECT_COLOR }} />
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, flex: 1 }}>Run a project</h2>
          {info.data?.project_id && (
            <a href={`/projects/${info.data.project_id}`} target="_blank" rel="noreferrer"
              className="btn-secondary text-xs" title="Open the called project in a new tab">
              <ExternalLink size={12} /> Open {info.data.name}
            </a>
          )}
          <button type="button" onClick={onClose} style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={16} /></button>
        </div>
        <p style={hint}>
          This step runs another project. Only the environment is passed implicitly; give its parameters and
          variables below. The called project keeps its own secrets.
        </p>

        <label style={label}>Step name</label>
        <input style={{ ...input, width: '100%', fontFamily: 'monospace' }} value={stepName} onChange={e => setStepName(e.target.value)} />

        <label style={label}>Project</label>
        <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
          <select aria-label="Reference" style={{ ...input, width: 230 }} value={ref}
            onChange={e => setRef(e.target.value as 'path' | 'name')}>
            <option value="path">by path (portable with git)</option>
            <option value="name">by name in the Studio workspace</option>
          </select>
          <select aria-label="Workspace project" style={{ ...input, flex: 1 }} value=""
            onChange={e => { const p = projects.find(x => x.id === e.target.value); if (p) choose(p) }}>
            <option value="">Choose an open project…</option>
            {projects.filter(p => p.id !== masterProjectId).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <input aria-label="Project reference" style={{ ...input, width: '100%', fontFamily: 'monospace' }} value={project}
          onChange={e => setProject(e.target.value)}
          placeholder={ref === 'path' ? '../crm-sync  (relative to this project)' : 'crm-sync'} />
        <div style={{ ...hint, marginTop: 4, minHeight: 16 }}>
          {info.isFetching && <span><Loader2 size={11} /> Checking…</span>}
          {!info.isFetching && info.data?.path && (
            <span>→ <b>{info.data.name}</b> <code>{info.data.path}</code>
              {ref === 'path' && info.data.relative && info.data.relative !== project && <> · saved as <code>{info.data.relative}</code></>}</span>
          )}
        </div>
        {info.data?.tree && info.data.tree.length > 1 && (
          <div style={{ ...hint, fontFamily: 'monospace', marginTop: 2 }}>
            {info.data.tree.map((t, i) => <div key={i}>{'  '.repeat(t.depth)}↳ {t.label}</div>)}
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <label style={label}>Environment</label>
            <select aria-label="Environment" style={{ ...input, width: 180 }} value={env} onChange={e => setEnv(e.target.value)}>
              <option value="inherit">inherit (same as this run)</option>
              <option value="none">none</option>
              {envChoices.map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div>
            <label style={label}>Run in</label>
            <select aria-label="Isolation" style={{ ...input, width: 170 }} value={isolation} onChange={e => setIsolation(e.target.value as 'inprocess' | 'subprocess')}>
              <option value="inprocess">this process (default)</option>
              <option value="subprocess">a separate process</option>
            </select>
          </div>
          <div>
            <label style={label}>Timeout</label>
            <input aria-label="Timeout" style={{ ...input, width: 90 }} value={timeout} placeholder="30m" onChange={e => setTimeoutV(e.target.value)} />
          </div>
          <div>
            <label style={label}>If already running</label>
            <select aria-label="Overlap" style={{ ...input, width: 120 }} value={overlap} onChange={e => setOverlap(e.target.value as 'wait' | 'skip' | 'fail')}>
              <option value="wait">wait</option><option value="skip">skip</option><option value="fail">fail</option>
            </select>
          </div>
          <div>
            <label style={label}>On failure</label>
            <select aria-label="On failure" style={{ ...input, width: 110 }} value={onFailure} onChange={e => setOnFailure(e.target.value)}>
              <option value="fail">fail</option><option value="skip">skip</option><option value="continue">continue</option>
            </select>
          </div>
        </div>
        <div style={{ ...hint, marginTop: 4 }}>Steps that run in parallel always use a separate process.</div>

        {(info.data?.workflows?.length ?? 0) > 0 && (<>
          <label style={label}>Workflows to run <span style={hint}>(none checked: the project's thread.yaml)</span></label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {info.data!.workflows.map(w => (
              <label key={w} style={{ fontSize: 12, display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                <input type="checkbox" checked={workflows.includes(w)}
                  onChange={e => setWorkflows(ws => e.target.checked ? [...ws, w] : ws.filter(x => x !== w))} /> {w}
              </label>
            ))}
          </div>
        </>)}

        <label style={label}>Parameters <span style={hint}>(passed to the project; empty = its own value)</span></label>
        {declNames.length > 0 && (
          <table data-testid="project-step-params" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginBottom: 6 }}>
            <tbody>
              {declNames.map(n => {
                const d = decls[n] ?? {}
                return (
                  <tr key={n}>
                    <td style={{ padding: 3, fontFamily: 'monospace', width: 170 }}>{n}{d.required ? ' *' : ''}</td>
                    <td style={{ padding: 3, width: 60, ...hint }}>{String(d.type ?? 'any')}</td>
                    <td style={{ padding: 3 }}>
                      <input style={{ ...input, width: '100%', borderColor: missingRequired.includes(n) ? 'var(--error)' : 'var(--bg-border)' }}
                        aria-label={`Parameter ${n}`} value={params[n] ?? ''}
                        placeholder={d.default != null ? `default: ${String(d.default)}` : d.required ? 'required' : ''}
                        onChange={e => setParams(p => ({ ...p, [n]: e.target.value }))} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {kvRows(extraParams, setExtraParams, ['other_param', 'value or {{ param:x }}'], 'project-step-extra-params')}

        <label style={label}>Variables <span style={hint}>(environment variables lent for this run; no secrets)</span></label>
        {kvRows(variables, setVariables, ['API_URL', 'value or ${ENV:X}'], 'project-step-variables')}

        <label style={label}>Outputs <span style={hint}>(parameters published by the project, read here as {'{{ project:'}{stepName || 'step'}{'.param.NAME }}'})</span></label>
        <input aria-label="Outputs" style={{ ...input, width: '100%', fontFamily: 'monospace' }} value={outputs}
          placeholder="last_id, batch_count" onChange={e => setOutputs(e.target.value)} />

        {(errors.length > 0 || missingRequired.length > 0 || (info.data?.warnings?.length ?? 0) > 0) && (
          <div data-testid="project-step-problems" style={{ marginTop: 12, fontSize: 12 }}>
            {errors.map((e, i) => <div key={i} style={{ color: 'var(--error)' }}><AlertTriangle size={12} /> {e}</div>)}
            {missingRequired.length > 0 && (
              <div style={{ color: 'var(--warning)' }}><AlertTriangle size={12} /> Required by the project, without a value: {missingRequired.join(', ')} — the run will stop before starting it.</div>
            )}
            {(info.data?.warnings ?? []).map((w, i) => <div key={`w${i}`} style={{ color: 'var(--warning)' }}>{w}</div>)}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button type="button" className="btn-secondary text-xs" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary text-xs" disabled={!canSave} onClick={save}
            data-testid="project-step-save" style={{ background: PROJECT_COLOR, opacity: canSave ? 1 : 0.5 }}>
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
