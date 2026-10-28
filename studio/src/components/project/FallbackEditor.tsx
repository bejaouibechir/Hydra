/**
 * FallbackEditor — fallback d'un workflow du thread (thread.yaml → fallback).
 *
 * Remplaçants (essayés dans l'ordre, hors du thread), condition `when`
 * vérifiée juste avant le lancement (vérifiée en direct par l'API, avec un
 * assistant d'insertion), bascule après un échec, politique si une
 * vérification ne peut pas répondre.
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2, X } from 'lucide-react'
import { api, type ConditionHelp } from '@/lib/api'
import { fallbackError, type ThreadFallback } from '@/lib/thread'

interface Props {
  projectId: string
  name: string                       // workflow du thread
  fallback: ThreadFallback
  candidates: string[]               // remplaçants possibles
  inThread: string[]                 // pour signaler « leaves the thread »
  onChange: (fb: ThreadFallback | null) => void
}

const OPS = ['<', '<=', '>', '>=', '==', '!=']
const PLACEHOLDER: Record<string, string> = { bytes: '1MB', seconds: '24h', number: '10' }

const quote = (v: string) => `'${v.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`

/** Morceau de condition construit par l'assistant. */
export function conditionPart(fn: string, kind: 'bool' | 'bytes' | 'seconds' | 'number' | 'attr',
  arg: string, negate: boolean, op: string, value: string): string {
  if (kind === 'attr') {
    const v = fn === 'previous.status' ? quote(value || 'failed') : (value || '0')
    return `${fn} ${op} ${v}`
  }
  const call = `${fn}(${quote(arg)})`
  if (kind === 'bool') return negate ? `not ${call}` : call
  return `${call} ${op} ${value || PLACEHOLDER[kind]}`
}

export default function FallbackEditor({ projectId, name, fallback, candidates, inThread, onChange }: Props) {
  const help = useQuery({ queryKey: ['conditions', projectId], queryFn: () => api.projects.conditions(projectId), staleTime: 30_000 })
  const set = (patch: Partial<ThreadFallback>) => onChange({ ...fallback, ...patch })
  const when = fallback.when ?? ''

  // Vérification en direct de la condition (syntaxe + noms déclarés)
  const [status, setStatus] = useState<{ ok: boolean; error?: string | null } | null>(null)
  useEffect(() => {
    if (!when.trim()) { setStatus(null); return }
    let alive = true
    const t = setTimeout(() => {
      api.projects.checkCondition(projectId, when).then(r => { if (alive) setStatus(r) }).catch(() => {})
    }, 400)
    return () => { alive = false; clearTimeout(t) }
  }, [projectId, when])

  const input: React.CSSProperties = { background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12, outline: 'none' }
  const muted = { color: 'var(--text-muted)' }
  const err = fallbackError(fallback)

  return (
    <div data-testid={`fallback-editor-${name}`} className="text-xs"
      style={{ margin: '2px 0 6px 22px', padding: '8px 10px', borderRadius: 8, border: '1px dashed var(--warning)', background: 'var(--bg-hover)' }}>
      <div className="flex items-center gap-2 flex-wrap" style={{ marginBottom: 6 }}>
        <b style={{ color: 'var(--warning)' }}>Fallback</b>
        <span style={muted}>replace with</span>
        {fallback.use.map((u, i) => (
          <span key={u} className="inline-flex items-center gap-1"
            style={{ fontFamily: 'monospace', padding: '1px 6px', borderRadius: 6, border: '1px dashed var(--warning)', background: 'var(--bg-card)' }}>
            {i > 0 && <span style={muted}>then</span>} {u}
            <button aria-label={`Remove ${u}`} title="Remove this replacement" style={{ ...muted, cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
              onClick={() => set({ use: fallback.use.filter(x => x !== u) })}><X size={11} /></button>
          </span>
        ))}
        <select style={input} value="" aria-label={`Add a fallback for ${name}`}
          onChange={e => { if (e.target.value) set({ use: [...fallback.use, e.target.value] }) }}>
          <option value="">+ add a workflow…</option>
          {candidates.map(c => (
            <option key={c} value={c}>{c}{inThread.includes(c) ? ' (leaves the thread)' : ''}</option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        <button className="btn-ghost text-xs !py-0.5" style={{ color: 'var(--error)' }} onClick={() => onChange(null)}
          title="Remove the fallback (the replacement workflows are kept, outside the thread)">
          <Trash2 size={11} /> Remove fallback
        </button>
      </div>

      <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
        <span style={muted}>when</span>
        <input style={{ ...input, flex: 1, fontFamily: 'monospace',
          borderColor: status && !status.ok ? 'var(--error)' : 'var(--bg-border)' }}
          value={when} aria-label={`${name} fallback condition`}
          placeholder="not source_available('crm_db')"
          title="Checked just before the workflow starts. If true, the first replacement runs instead."
          onChange={e => set({ when: e.target.value })} />
        {status && (status.ok
          ? <span style={{ color: 'var(--success)' }}>✓</span>
          : <span style={{ color: 'var(--error)' }} title={status.error ?? ''}>✗</span>)}
      </div>
      {status && !status.ok && <div style={{ color: 'var(--error)', margin: '0 0 4px 38px', fontFamily: 'monospace' }}>{status.error}</div>}
      {help.data && <ConditionBuilder help={help.data} onInsert={(part, join) =>
        set({ when: when.trim() ? `${when.trim()} ${join} ${part}` : part })} />}

      <div className="flex items-center gap-3 flex-wrap" style={{ marginTop: 6 }}>
        <label className="inline-flex items-center gap-1" title={`If ${name} fails (or exceeds its max time) without leaving anything published — nothing loaded and nothing done outside Hydra ETL, or everything undone by rollback: true — the first replacement runs; if it fails too, the next one. If ${name} had already published data, the project stops and says why.`}>
          <input type="checkbox" checked={!!fallback.on_failure} aria-label={`${name} fallback on failure`}
            onChange={e => set({ on_failure: e.target.checked })} />
          also after a failure <span style={muted}>(only if nothing was published)</span>
        </label>
        <label className="inline-flex items-center gap-1">
          <span style={muted}>if a check cannot answer</span>
          <select style={input} value={fallback.on_probe_error ?? 'keep'} aria-label={`${name} on probe error`}
            onChange={e => set({ on_probe_error: e.target.value as 'keep' | 'replace' })}>
            <option value="keep">keep {name}</option>
            <option value="replace">use the fallback</option>
          </select>
        </label>
      </div>
      {err && <div style={{ color: 'var(--error)', marginTop: 4 }}>✗ {err}</div>}
    </div>
  )
}

/** Assistant : fonction + argument (+ comparaison) → morceau ajouté à la condition. */
function ConditionBuilder({ help, onInsert }: { help: ConditionHelp; onInsert: (part: string, join: 'or' | 'and') => void }) {
  const [fn, setFn] = useState(help.functions[0]?.name ?? 'source_available')
  const [arg, setArg] = useState('')
  const [negate, setNegate] = useState(true)
  const [op, setOp] = useState('<')
  const [value, setValue] = useState('')
  const [join, setJoin] = useState<'or' | 'and'>('or')
  const f = help.functions.find(x => x.name === fn)
  const kind = f ? f.returns : 'attr'
  const choices = !f ? [] : f.arg === 'source' ? help.sources : f.arg === 'destination' ? help.destinations
    : f.arg === 'database' ? [...new Set([...help.sources, ...help.destinations])] : f.arg === 'secret' ? help.secrets : []
  const input: React.CSSProperties = { background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '2px 5px', color: 'var(--text-primary)', fontSize: 11, outline: 'none' }
  const listId = `cond-args-${fn}`
  const needsArg = !!f && !arg.trim()

  return (
    <div data-testid="condition-builder" className="flex items-center gap-1.5 flex-wrap" style={{ margin: '0 0 0 38px', color: 'var(--text-muted)' }}>
      <span>insert</span>
      <select style={input} value={join} aria-label="Join with" onChange={e => setJoin(e.target.value as 'or' | 'and')}>
        <option value="or">or</option><option value="and">and</option>
      </select>
      {kind === 'bool' && (
        <label className="inline-flex items-center gap-1"><input type="checkbox" checked={negate} onChange={e => setNegate(e.target.checked)} />not</label>
      )}
      <select style={input} value={fn} aria-label="Condition function" title={f?.help ?? help.attributes[fn]}
        onChange={e => { setFn(e.target.value); setArg(''); setValue(''); setOp(e.target.value === 'previous.status' ? '==' : '<') }}>
        {help.functions.map(x => <option key={x.name} value={x.name} title={x.help}>{x.name}(…)</option>)}
        {Object.keys(help.attributes).map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      {f && <>
        <input style={{ ...input, width: 130 }} value={arg} list={listId} aria-label="Condition argument"
          placeholder={f.arg} onChange={e => setArg(e.target.value)} />
        <datalist id={listId}>{choices.map(c => <option key={c} value={c} />)}</datalist>
      </>}
      {kind !== 'bool' && <>
        <select style={input} value={op} aria-label="Comparison" onChange={e => setOp(e.target.value)}>
          {(fn === 'previous.status' ? ['==', '!='] : OPS).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        <input style={{ ...input, width: 70 }} value={value} aria-label="Compared value"
          placeholder={fn === 'previous.status' ? 'failed' : kind === 'attr' ? '100' : PLACEHOLDER[kind]}
          onChange={e => setValue(e.target.value)} />
      </>}
      <button className="btn-ghost text-xs !py-0.5" disabled={needsArg}
        title={f?.help ?? help.attributes[fn]}
        onClick={() => onInsert(conditionPart(fn, kind as 'bool', arg.trim(), negate,
          fn === 'previous.status' && !['==', '!='].includes(op) ? '==' : op, value.trim()), join)}>
        <Plus size={11} /> Insert
      </button>
    </div>
  )
}
