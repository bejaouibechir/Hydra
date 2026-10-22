/**
 * ThreadEditor — ordre d'exécution des workflows d'un projet
 * (workflows/thread.yaml), lu par `hdrctl run <projet>` et par « Run project ».
 *
 * Onglet Define : étapes lancées l'une après l'autre ; dans une étape, les
 * workflows tournent l'un après l'autre (sequential) ou en même temps
 * (parallel) ; délai après une étape ; workflows actifs ou sautés ; boucles
 * (rejouer une portion du thread N fois). Onglet Preview : le schéma.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, CheckCircle2, Layers, Play, Plus, Save, X, AlertTriangle, Repeat } from 'lucide-react'
import { api } from '@/lib/api'
import {
  appendWorkflow, forSave, isValidDelay, loopErrors, loopsForSave, moveWorkflow, namesIn,
  pruneLoops, removeWorkflow, type ThreadLoop, type ThreadStage,
} from '@/lib/thread'
import ThreadPreview from '@/components/project/ThreadPreview'
import Spinner from '@/components/ui/Spinner'

interface Props {
  projectId: string
  projectPath: string
  /** nom du workflow (fichier) → id Studio, pour ouvrir un bloc du schéma */
  workflowIds?: Record<string, string>
}

export default function ThreadEditor({ projectId, projectPath, workflowIds = {} }: Props) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['thread', projectId], queryFn: () => api.projects.thread(projectId) })
  const [tab, setTab] = useState<'define' | 'preview'>('define')
  const [stages, setStages] = useState<ThreadStage[]>([])
  const [loops, setLoops] = useState<ThreadLoop[]>([])
  const [dirty, setDirty] = useState(false)
  const [check, setCheck] = useState<{ ok: boolean; errors: string[]; active: string[] } | null>(null)

  useEffect(() => {
    if (q.data && !dirty) {
      setStages(q.data.thread.thread)
      setLoops(q.data.thread.loops ?? [])
    }
  }, [q.data, dirty])

  const edit = (next: ThreadStage[]) => {
    setStages(next); setLoops(l => pruneLoops(next, l)); setDirty(true); setCheck(null)
  }
  const editLoops = (next: ThreadLoop[]) => { setLoops(next); setDirty(true); setCheck(null) }
  const missing = new Set(q.data?.missing ?? [])
  const onDisk = q.data?.workflows ?? []
  const inThread = namesIn(stages)
  const notInThread = useMemo(() => onDisk.filter(n => !inThread.includes(n)), [onDisk, inThread])
  const delaysOk = stages.every(s => isValidDelay(s.delay_after ?? ''))
  const lErrors = loopErrors(stages, loops)
  const valid = delaysOk && lErrors.every(e => e === null)

  const save = useMutation({
    mutationFn: () => api.projects.saveThread(projectId, forSave(stages), loopsForSave(loops)),
    onSuccess: d => { qc.setQueryData(['thread', projectId], d); setDirty(false) },
  })
  const checkMut = useMutation({
    mutationFn: async () => { if (dirty) await save.mutateAsync(); return api.projects.check(projectId) },
    onSuccess: setCheck,
  })
  const run = useMutation({
    mutationFn: async () => {
      if (dirty) await save.mutateAsync()
      const c = await api.projects.check(projectId)
      setCheck(c)
      if (!c.ok) throw new Error('The project has errors: nothing was started.')
      return api.runs.start({ workflow_path: projectPath })
    },
    onSuccess: r => navigate(`/runs/${r.run_id}`),
  })

  const box: React.CSSProperties = { border: '1px solid var(--bg-border)', borderRadius: 10, background: 'var(--bg-card)' }
  const iconBtn: React.CSSProperties = { width: 22, height: 22, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }
  const input: React.CSSProperties = { background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }
  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: '4px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', borderRadius: 7, border: 'none',
    background: active ? 'var(--primary)' : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })
  const err = (save.error || run.error || checkMut.error) as Error | null

  if (q.isLoading) return <div className="flex justify-center py-6"><Spinner /></div>
  if (q.error) return <p className="text-xs" style={{ color: 'var(--error)' }}>{(q.error as Error).message}</p>

  return (
    <section data-testid="thread-editor" style={{ ...box, padding: 14, marginBottom: 20 }}>
      <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
        <Layers size={16} style={{ color: 'var(--primary)' }} />
        <h2 className="font-semibold text-sm" style={{ margin: 0, color: 'var(--text-primary)' }}>Execution order</h2>
        <code className="text-xs" style={{ color: 'var(--text-muted)' }}>workflows/thread.yaml</code>
        <div style={{ display: 'inline-flex', gap: 2, background: 'var(--bg-hover)', borderRadius: 9, padding: 2, marginLeft: 8 }}>
          <button type="button" style={tabBtn(tab === 'define')} onClick={() => setTab('define')}>Define</button>
          <button type="button" style={tabBtn(tab === 'preview')} onClick={() => setTab('preview')}>Preview</button>
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn-secondary text-xs !py-1" onClick={() => checkMut.mutate()} disabled={checkMut.isPending || !valid}>
          <CheckCircle2 size={13} /> Check
        </button>
        <button className="btn-secondary text-xs !py-1" onClick={() => save.mutate()} disabled={!dirty || save.isPending || !valid}>
          {save.isPending ? <Spinner size="sm" /> : <Save size={13} />} {dirty ? 'Save' : 'Saved'}
        </button>
        <button className="btn-primary text-xs !py-1" onClick={() => run.mutate()} disabled={run.isPending || !valid}
          style={{ background: 'var(--success)', borderColor: 'var(--success)' }}
          title="Run every active workflow in this order (like hdrctl run)">
          {run.isPending ? <Spinner size="sm" /> : <Play size={13} fill="currentColor" />} Run project
        </button>
      </div>

      {tab === 'preview' ? (
        <ThreadPreview stages={stages} loops={loops} missing={missing}
          onOpen={name => { const id = workflowIds[name]; if (id) navigate(`/workflows/${id}?projectId=${projectId}`) }} />
      ) : (
        <>
          <p className="text-xs" style={{ color: 'var(--text-muted)', margin: '0 0 10px' }}>
            Stages run one after the other. In a stage, workflows run one after the other (sequential) or at the
            same time (parallel). Untick a workflow to skip it. A failed workflow stops the project.
            {q.data?.implicit && <> No thread.yaml yet: workflows run in alphabetical order until you save.</>}
          </p>

          {stages.map((st, si) => (
            <div key={si} style={{ ...box, padding: '8px 10px', marginBottom: 8 }}>
              <div className="flex items-center gap-2 text-xs" style={{ marginBottom: 6 }}>
                <b style={{ color: 'var(--text-secondary)' }}>Stage {si + 1}</b>
                <select style={input} value={st.mode} aria-label={`Stage ${si + 1} mode`}
                  onChange={e => edit(stages.map((s, i) => i === si ? { ...s, mode: e.target.value as ThreadStage['mode'] } : s))}>
                  <option value="sequential">sequential</option>
                  <option value="parallel">parallel</option>
                </select>
                <span style={{ color: 'var(--text-muted)' }}>then wait</span>
                <input style={{ ...input, width: 70, borderColor: isValidDelay(st.delay_after ?? '') ? 'var(--bg-border)' : 'var(--error)' }}
                  value={st.delay_after ?? ''} placeholder="0" aria-label={`Stage ${si + 1} delay`}
                  title="Pause before the next stage: seconds, or 30s / 5m / 1h"
                  onChange={e => edit(stages.map((s, i) => i === si ? { ...s, delay_after: e.target.value } : s))} />
                <div style={{ flex: 1 }} />
                <button style={iconBtn} title="Remove this stage (its workflows leave the thread)"
                  onClick={() => edit(stages.filter((_, i) => i !== si))}><X size={12} /></button>
              </div>
              {st.workflows.length === 0 && <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Empty stage (dropped on save).</div>}
              {st.workflows.map((w, wi) => (
                <div key={w.name} className="flex items-center gap-2 text-xs" style={{ padding: '3px 0' }}>
                  <input type="checkbox" checked={w.active} title={w.active ? 'Active' : 'Skipped'}
                    aria-label={`${w.name} active`}
                    onChange={e => edit(stages.map((s, i) => i !== si ? s : {
                      ...s, workflows: s.workflows.map((x, j) => j === wi ? { ...x, active: e.target.checked } : x),
                    }))} />
                  <span style={{ fontFamily: 'monospace', color: w.active ? 'var(--text-primary)' : 'var(--text-muted)', textDecoration: w.active ? 'none' : 'line-through' }}>{w.name}</span>
                  {missing.has(w.name) && <span style={{ color: 'var(--error)' }}><AlertTriangle size={11} style={{ display: 'inline' }} /> file missing</span>}
                  <div style={{ flex: 1 }} />
                  <button style={iconBtn} title="Move up" onClick={() => edit(moveWorkflow(stages, si, wi, -1))}><ArrowUp size={12} /></button>
                  <button style={iconBtn} title="Move down" onClick={() => edit(moveWorkflow(stages, si, wi, 1))}><ArrowDown size={12} /></button>
                  <button style={iconBtn} title="Remove from the thread (the workflow is kept)" onClick={() => edit(removeWorkflow(stages, si, wi))}><X size={12} /></button>
                </div>
              ))}
            </div>
          ))}

          <div className="flex items-center gap-2 flex-wrap text-xs">
            <button className="btn-ghost text-xs !py-1" onClick={() => edit([...stages, { mode: 'parallel', workflows: [] }])}>
              <Plus size={12} /> Add stage
            </button>
            {notInThread.length > 0 && <span style={{ color: 'var(--text-muted)' }}>Not in the thread (not run):</span>}
            {notInThread.map(n => (
              <button key={n} className="btn-ghost text-xs !py-1" title="Add at the end" onClick={() => edit(appendWorkflow(stages, n))}
                style={{ fontFamily: 'monospace' }}>
                <Plus size={11} /> {n}
              </button>
            ))}
          </div>

          {/* ── Boucles ─────────────────────────────────────────────── */}
          <div data-testid="thread-loops" style={{ ...box, padding: '8px 10px', marginTop: 10 }}>
            <div className="flex items-center gap-2 text-xs" style={{ marginBottom: loops.length ? 6 : 0 }}>
              <Repeat size={13} style={{ color: 'var(--primary)' }} />
              <b style={{ color: 'var(--text-secondary)' }}>Loops</b>
              <span style={{ color: 'var(--text-muted)' }}>replay a part of the thread, from one workflow back to an earlier one (optional)</span>
              <div style={{ flex: 1 }} />
              <button className="btn-ghost text-xs !py-1" disabled={inThread.length === 0}
                onClick={() => editLoops([...loops, { from: inThread[inThread.length - 1], to: inThread[0], times: 2 }])}>
                <Plus size={12} /> Add loop
              </button>
            </div>
            {loops.map((lp, li) => (
              <div key={li} className="flex items-center gap-2 text-xs flex-wrap" style={{ padding: '3px 0' }}>
                <span style={{ color: 'var(--text-muted)' }}>After</span>
                <select style={input} value={lp.from} aria-label={`Loop ${li + 1} from`}
                  onChange={e => editLoops(loops.map((x, i) => i === li ? { ...x, from: e.target.value } : x))}>
                  {inThread.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
                <span style={{ color: 'var(--text-muted)' }}>go back to</span>
                <select style={input} value={lp.to} aria-label={`Loop ${li + 1} to`}
                  onChange={e => editLoops(loops.map((x, i) => i === li ? { ...x, to: e.target.value } : x))}>
                  {inThread.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
                <span style={{ color: 'var(--text-muted)' }}>— passes in total</span>
                <input type="number" min={1} max={1000} style={{ ...input, width: 60 }} value={lp.times}
                  aria-label={`Loop ${li + 1} times`}
                  onChange={e => editLoops(loops.map((x, i) => i === li ? { ...x, times: Number(e.target.value) } : x))} />
                <span style={{ color: 'var(--text-muted)' }}>pause before each repeat</span>
                <input style={{ ...input, width: 70, borderColor: isValidDelay(lp.delay ?? '') ? 'var(--bg-border)' : 'var(--error)' }}
                  value={lp.delay ?? ''} placeholder="0" aria-label={`Loop ${li + 1} delay`}
                  onChange={e => editLoops(loops.map((x, i) => i === li ? { ...x, delay: e.target.value } : x))} />
                <button style={iconBtn} title="Remove this loop" onClick={() => editLoops(loops.filter((_, i) => i !== li))}><X size={12} /></button>
                {lErrors[li] && <span style={{ color: 'var(--error)' }}>✗ {lErrors[li]}</span>}
              </div>
            ))}
          </div>
        </>
      )}

      {check && (
        <div className="text-xs" style={{ marginTop: 10, color: check.ok ? 'var(--success)' : 'var(--error)' }}>
          {check.ok
            ? <>✓ Ready: {check.active.length ? check.active.join(' → ') : 'no active workflow'}{loops.length ? ` (+ ${loops.length} loop${loops.length > 1 ? 's' : ''})` : ''}</>
            : check.errors.map((e, i) => <div key={i} style={{ fontFamily: 'monospace' }}>✗ {e}</div>)}
        </div>
      )}
      {err && <p className="text-xs" style={{ marginTop: 8, color: 'var(--error)' }}>{err.message}</p>}
    </section>
  )
}
