/**
 * TriggersPanel — Project settings › Triggers (triggers.yaml, Hydra 0.19).
 *
 * Les déclencheurs qui lancent le projet entier : heure, intervalle, fichier,
 * fichier témoin, changement d'une source, appel HTTP, fin d'un autre projet.
 * - liste : événement, ce qui est lancé, prochaine échéance, dernier run ;
 * - ajouter / modifier (TriggerDialog), activer, supprimer : chaque changement
 *   écrit triggers.yaml (l'ancien fichier est copié dans ~/.hydra/_backups) ;
 * - Run now ; jeton d'un webhook (affiché une seule fois) ; historique.
 * Le moteur de `hdrctl serve` relit le fichier de lui-même. Rafraîchi toutes les 5 s.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Copy, KeyRound, Loader2, Pencil, Play, Plus, RefreshCw, Trash2, X, Zap,
} from 'lucide-react'
import { api, ApiError, type TriggerInfo, type TriggerRun, type TriggerToken } from '@/lib/api'
import { typeMeta, type TriggerConfig } from '@/lib/triggers'
import TriggerDialog from './TriggerDialog'

interface Props { projectId: string }

const STATUS: Record<string, { mark: string; color: string }> = {
  success: { mark: '✓', color: 'var(--success)' },
  failed: { mark: '✗', color: 'var(--error)' },
  skipped: { mark: '⏭', color: 'var(--warning)' },
}

function ago(iso?: string | null): string {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (Number.isNaN(s)) return iso
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(iso).toLocaleString()
}
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '')
const errorsOf = (e: unknown): string[] => {
  if (e instanceof ApiError) {
    const d = e.detail as { errors?: unknown } | null
    if (d && Array.isArray(d.errors)) return d.errors.map(String)
  }
  return [(e as Error)?.message ?? String(e)]
}

export default function TriggersPanel({ projectId }: Props) {
  const qc = useQueryClient()
  const key = ['triggers', projectId]
  const q = useQuery({ queryKey: key, queryFn: () => api.triggers.list(projectId), refetchInterval: 5000 })
  const [historyOf, setHistoryOf] = useState('')
  const hist = useQuery({
    queryKey: ['trigger-history', projectId, historyOf],
    queryFn: () => api.triggers.history(projectId, historyOf || undefined, 30), refetchInterval: 5000,
  })
  const envNames = useQuery({ queryKey: ['env-names', projectId], queryFn: () => api.globalEnv.names(projectId) })
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects.list })
  const [editing, setEditing] = useState<TriggerConfig | 'new' | null>(null)
  const [tokenFor, setTokenFor] = useState<TriggerInfo | null>(null)
  const [saveErrors, setSaveErrors] = useState<string[]>([])
  const [fired, setFired] = useState<Record<string, string>>({})

  const configs = (q.data?.triggers ?? []).map(t => t.config as TriggerConfig)
  const save = useMutation({
    mutationFn: (list: TriggerConfig[]) => api.triggers.save(projectId, list),
    onSuccess: d => { qc.setQueryData(key, d); setSaveErrors([]); setEditing(null) },
    onError: e => setSaveErrors(errorsOf(e)),
  })
  const fire = useMutation({
    mutationFn: (name: string) => api.triggers.fire(projectId, name),
    onSuccess: (_d, name) => { setFired(f => ({ ...f, [name]: 'started' })); qc.invalidateQueries({ queryKey: key }) },
    onError: (e, name) => setFired(f => ({ ...f, [name]: (e as Error).message })),
  })

  const replace = (name: string | null, c: TriggerConfig | null) => {
    const list = configs.filter(x => x.name !== name)
    if (c) {
      const i = name ? configs.findIndex(x => x.name === name) : -1
      if (i >= 0) list.splice(i, 0, c)
      else list.push(c)
    }
    save.mutate(list)
  }
  const toggle = (t: TriggerInfo) => {
    const c = { ...(t.config as TriggerConfig) }
    if (t.enabled) c.enabled = false
    else delete c.enabled
    replace(t.name, c)
  }

  const muted: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }
  const iconBtn: React.CSSProperties = { width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }

  if (q.isLoading) return <div style={{ ...muted, display: 'flex', gap: 6 }}><Loader2 size={13} /> Loading…</div>
  if (q.isError) return <div style={{ fontSize: 12, color: 'var(--error)' }}>{(q.error as Error).message}</div>
  const d = q.data!
  const envs = Array.from(new Set((envNames.data ?? []).map(n => n.name))).sort()

  return (
    <div data-testid="triggers-panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <Zap size={15} style={{ color: 'var(--primary)' }} />
        <span style={{ fontSize: 13, fontWeight: 700 }}>Triggers</span>
        <code style={muted}>{d.file}</code>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn-secondary text-xs" onClick={() => q.refetch()} title="Refresh">
          <RefreshCw size={12} /> Refresh
        </button>
        <button type="button" className="btn-primary text-xs" data-testid="trigger-add" disabled={d.invalid}
          onClick={() => { setSaveErrors([]); setEditing('new') }}>
          <Plus size={12} /> Add a trigger
        </button>
      </div>
      <p style={{ ...muted, lineHeight: 1.5, marginBottom: 10 }}>
        A trigger starts the whole project when its event happens. They run while <code>hdrctl serve</code> runs
        (this Studio) or in <code>hdrctl watch</code> — not both on the same project. Changes are written to
        triggers.yaml (comments in the file are not kept; the previous file is copied to ~/.hydra/_backups).
      </p>

      {(d.errors.length > 0 || saveErrors.length > 0) && (
        <div data-testid="trigger-errors" style={{ border: '1px solid var(--error)', borderRadius: 8, padding: '8px 10px', marginBottom: 10, fontSize: 12 }}>
          {d.invalid && <div style={{ fontWeight: 600, marginBottom: 4 }}>triggers.yaml cannot be read — fix it in an editor:</div>}
          {[...saveErrors, ...d.errors].map((e, i) => (
            <div key={i} style={{ color: 'var(--error)' }}><AlertTriangle size={12} style={{ display: 'inline', verticalAlign: '-2px' }} /> {e}</div>
          ))}
        </div>
      )}
      {d.warnings.length > 0 && (
        <div style={{ marginBottom: 10, fontSize: 12 }}>
          {d.warnings.map((w, i) => <div key={i} style={{ color: 'var(--warning)' }}>⚠ {w}</div>)}
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }} data-testid="triggers-table">
        <thead>
          <tr>
            {['', 'Trigger', 'When', 'Runs', 'Next', 'Last run', ''].map((h, i) => (
              <th key={i} style={{ ...muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', padding: '0 6px 6px' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.triggers.map(t => {
            const meta = typeMeta(t.type)
            const last = t.last
            const st = last ? STATUS[last.status] ?? STATUS.failed : null
            return (
              <tr key={t.name} data-testid={`trigger-row-${t.name}`} style={{ borderTop: '1px solid var(--bg-border)', opacity: t.enabled ? 1 : 0.55 }}>
                <td style={{ padding: '6px', width: 34 }}>
                  <input type="checkbox" checked={t.enabled} title={t.enabled ? 'Enabled — click to turn off' : 'Off — click to enable'}
                    aria-label={`Enable ${t.name}`} disabled={save.isPending} onChange={() => toggle(t)} />
                </td>
                <td style={{ padding: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 5, background: meta.color, flexShrink: 0 }} />
                    <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{t.name}</span>
                    <span style={{ ...muted, fontSize: 10, border: `1px solid ${meta.color}`, borderRadius: 10, padding: '0 6px', color: meta.color }}>{t.type}</span>
                  </div>
                  {t.description && <div style={muted}>{t.description}</div>}
                </td>
                <td style={{ padding: 6 }}>
                  {t.when}
                  {t.type === 'webhook' && (
                    <div style={{ ...muted, color: t.token_set ? 'var(--success)' : 'var(--warning)' }}>
                      {t.token_set ? 'token set' : 'no token yet'}
                    </div>
                  )}
                </td>
                <td style={{ padding: 6 }}>
                  <div>{t.workflows?.length ? t.workflows.join(', ') : <span style={muted}>thread.yaml</span>}</div>
                  <div style={muted}>env: {t.env || 'from serve'}</div>
                </td>
                <td style={{ padding: 6, whiteSpace: 'nowrap' }}>
                  {t.running ? <span style={{ color: 'var(--info)' }}><Loader2 size={12} style={{ display: 'inline' }} /> running</span>
                    : t.next ? when(t.next)
                    : <span style={muted}>{t.note && t.enabled && !t.note.startsWith('type webhook') ? t.note : t.type === 'webhook' ? 'on call' : t.enabled ? 'on event' : 'off'}</span>}
                </td>
                <td style={{ padding: 6 }}>
                  {last && st ? (
                    <span title={last.error ?? last.detail ?? ''}>
                      <span style={{ color: st.color, fontWeight: 700 }}>{st.mark}</span> {ago(last.at)}
                      <span style={muted}> · {last.origin}</span>
                    </span>
                  ) : <span style={muted}>—</span>}
                  {fired[t.name] && <div style={{ ...muted, color: fired[t.name] === 'started' ? 'var(--info)' : 'var(--error)' }}>{fired[t.name]}</div>}
                </td>
                <td style={{ padding: 6, whiteSpace: 'nowrap', textAlign: 'right' }}>
                  <span style={{ display: 'inline-flex', gap: 4 }}>
                    <button type="button" style={{ ...iconBtn, color: 'var(--success)' }} title="Run now" aria-label={`Run ${t.name} now`}
                      disabled={t.running || fire.isPending} onClick={() => fire.mutate(t.name)}><Play size={12} /></button>
                    {t.type === 'webhook' && (
                      <button type="button" style={iconBtn} title="Webhook token" aria-label={`Token of ${t.name}`}
                        onClick={() => setTokenFor(t)}><KeyRound size={12} /></button>
                    )}
                    <button type="button" style={iconBtn} title="Edit" aria-label={`Edit ${t.name}`}
                      onClick={() => { setSaveErrors([]); setEditing(t.config as TriggerConfig) }}><Pencil size={12} /></button>
                    <button type="button" style={iconBtn} title="Delete" aria-label={`Delete ${t.name}`}
                      onClick={() => { if (window.confirm(`Delete the trigger '${t.name}'?`)) replace(t.name, null) }}><Trash2 size={12} /></button>
                  </span>
                </td>
              </tr>
            )
          })}
          {d.triggers.length === 0 && !d.invalid && (
            <tr><td colSpan={7} style={{ padding: 12, ...muted }}>
              No trigger yet: the project runs only when someone starts it. Add one to run it at a time, when a file
              arrives, when a source changes, on a webhook call or after another project.
            </td></tr>
          )}
        </tbody>
      </table>

      <History runs={hist.data ?? []} names={d.triggers.map(t => t.name)} value={historyOf} onChange={setHistoryOf} />

      {editing && (
        <TriggerDialog
          initial={editing === 'new' ? null : editing}
          otherNames={configs.map(c => c.name).filter(n => editing === 'new' || n !== editing.name)}
          workflows={d.workflows} sources={d.sources} envs={envs}
          projects={projects.data ?? []} currentProjectId={projectId}
          onClose={() => setEditing(null)}
          onSave={c => replace(editing === 'new' ? null : editing.name, c)}
        />
      )}
      {editing && saveErrors.length > 0 && (
        <div style={{ position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 1100,
          background: 'var(--bg-card)', border: '1px solid var(--error)', borderRadius: 8, padding: '8px 12px', fontSize: 12, maxWidth: 640 }}>
          {saveErrors.map((e, i) => <div key={i} style={{ color: 'var(--error)' }}>{e}</div>)}
        </div>
      )}
      {tokenFor && <TokenDialog projectId={projectId} trigger={tokenFor} onClose={() => { setTokenFor(null); qc.invalidateQueries({ queryKey: key }) }} />}
    </div>
  )
}

function History({ runs, names, value, onChange }: { runs: TriggerRun[]; names: string[]; value: string; onChange: (v: string) => void }) {
  const muted: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }
  return (
    <div style={{ marginTop: 18 }} data-testid="trigger-history">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 700 }}>History</span>
        <select aria-label="History of" value={value} onChange={e => onChange(e.target.value)}
          style={{ background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12 }}>
          <option value="">all triggers</option>
          {names.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        <span style={muted}>.hydra/triggers/history.jsonl — this machine only</span>
      </div>
      {runs.length === 0 ? <div style={muted}>No run started by a trigger yet.</div> : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <tbody>
            {[...runs].reverse().map((r, i) => {
              const st = STATUS[r.status] ?? STATUS.failed
              return (
                <tr key={i} style={{ borderTop: '1px solid var(--bg-border)' }}>
                  <td style={{ padding: '4px 6px', color: st.color, fontWeight: 700, width: 18 }}>{st.mark}</td>
                  <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>{when(r.at)}</td>
                  <td style={{ padding: '4px 6px', fontFamily: 'monospace' }}>{r.trigger}</td>
                  <td style={{ padding: '4px 6px', ...muted }}>{r.origin}{(r.attempt ?? 1) > 1 ? ` · attempt ${r.attempt}` : ''}</td>
                  <td style={{ padding: '4px 6px', ...muted }}>{r.env ?? ''}</td>
                  <td style={{ padding: '4px 6px', ...muted }}>{r.duration != null ? `${r.duration}s` : ''}</td>
                  <td style={{ padding: '4px 6px', color: r.error ? 'var(--error)' : 'var(--text-muted)', fontSize: 11 }}>{r.error ?? r.detail ?? ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

function TokenDialog({ projectId, trigger, onClose }: { projectId: string; trigger: TriggerInfo; onClose: () => void }) {
  const [result, setResult] = useState<TriggerToken | null>(null)
  const [copied, setCopied] = useState(false)
  const make = useMutation({
    mutationFn: (rotate: boolean) => api.triggers.token(projectId, trigger.name, rotate),
    onSuccess: r => setResult(r),
  })
  const url = result ? `${window.location.origin}/api${result.url.replace(/^\/api/, '')}` : ''
  const muted: React.CSSProperties = { fontSize: 11, color: 'var(--text-muted)' }
  const copy = (s: string) => { navigator.clipboard?.writeText(s).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  const code: React.CSSProperties = { display: 'block', fontFamily: 'monospace', fontSize: 11, background: 'var(--bg-input)',
    border: '1px solid var(--bg-border)', borderRadius: 6, padding: '6px 8px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '4px 0 8px' }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} data-testid="token-dialog"
        style={{ width: 600, background: 'var(--bg-card)', borderRadius: 12, border: '1px solid #a855f7', padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <KeyRound size={16} style={{ color: '#a855f7' }} />
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, flex: 1 }}>Token of {trigger.name}</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={16} /></button>
        </div>
        {!result && (<>
          <p style={{ ...muted, lineHeight: 1.5 }}>
            The token is a random value saved as the project secret <code>{String(trigger.config.token ?? '').slice(9, -1)}</code>
            {' '}(.hydra/secrets, ignored by git). It is shown once; the caller sends it in the header <code>X-Hydra-Token</code>.
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            {!trigger.token_set
              ? <button type="button" className="btn-primary text-xs" data-testid="token-create" onClick={() => make.mutate(false)} disabled={make.isPending}>Create the token</button>
              : <button type="button" className="btn-primary text-xs" data-testid="token-rotate"
                  onClick={() => { if (window.confirm('Replace the token? The current one stops working.')) make.mutate(true) }} disabled={make.isPending}>
                  Replace the token
                </button>}
            {trigger.token_set && <span style={{ ...muted, alignSelf: 'center' }}>A token is set. Its value cannot be shown again.</span>}
          </div>
          {make.isError && <div style={{ color: 'var(--error)', fontSize: 12, marginTop: 8 }}>{(make.error as Error).message}</div>}
        </>)}
        {result && (
          <div data-testid="token-result">
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--warning)' }}>Copy it now — it is not shown again.</div>
            <code style={code} data-testid="token-value">{result.token}</code>
            <button type="button" className="btn-secondary text-xs" onClick={() => copy(result.token)}><Copy size={12} /> {copied ? 'Copied' : 'Copy the token'}</button>
            <div style={{ ...muted, marginTop: 12 }}>PowerShell</div>
            <code style={code}>{`Invoke-RestMethod -Method Post "${url}" -Headers @{ "X-Hydra-Token" = "<token>" }`}</code>
            <div style={muted}>curl</div>
            <code style={code}>{`curl -X POST "${url}" -H "X-Hydra-Token: <token>"`}</code>
            <div style={muted}>Saved as <code>{result.secret}</code> in <code>{result.file}</code>.</div>
          </div>
        )}
      </div>
    </div>
  )
}
