/**
 * EnvironmentsManager — Global settings › Environments.
 *
 * Crée, renomme et supprime les environnements (dev, prod…) et édite leurs
 * variables globales, partagées par tous les projets de la machine :
 *   ~/.hydra/env          variables communes (tous les environnements)
 *   ~/.hydra/env.<env>    variables d'un environnement
 * Enregistré sur la machine qui exécute Hydra (via l'API), pas dans le navigateur.
 * Les secrets n'ont rien à faire ici : Project settings › Secrets.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Save, Loader2, Pencil, Trash2, Check } from 'lucide-react'
import { api, type GlobalEnvInfo } from '@/lib/api'

const COMMON = ''
const NAME_RE = /^[A-Za-z0-9_][A-Za-z0-9_-]*$/
const VAR_RE = /^[A-Za-z_][A-Za-z0-9_]*$/

interface Row { id: number; key: string; value: string }
let _seq = 1

const toRows = (vars: Record<string, string>): Row[] =>
  Object.entries(vars).map(([key, value]) => ({ id: _seq++, key, value }))

export default function EnvironmentsManager() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['global-env'], queryFn: api.globalEnv.get })
  const [scope, setScope] = useState<string>(COMMON)
  const [rows, setRows] = useState<Row[]>([])
  const [dirty, setDirty] = useState(false)
  const [newName, setNewName] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  // Lien « Manage » du sélecteur d'environnement : /settings/global#environments
  useEffect(() => {
    if (window.location.hash === '#environments')
      document.getElementById('environments')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [q.isSuccess])

  const envs = useMemo(() => (q.data?.environments ?? []).map(e => e.name), [q.data])
  const current = scope === COMMON ? q.data?.common : q.data?.environments.find(e => e.name === scope)

  // Recharge le tableau quand on change d'onglet ou après un enregistrement
  useEffect(() => {
    if (!q.data) return
    if (scope !== COMMON && !envs.includes(scope)) { setScope(COMMON); return }
    setRows(toRows(current?.vars ?? {}))
    setDirty(false)
  }, [q.data, scope])                                 // eslint-disable-line react-hooks/exhaustive-deps

  const done = (d: GlobalEnvInfo, note?: string) => {
    qc.setQueryData(['global-env'], d)
    qc.invalidateQueries({ queryKey: ['env-names'] })
    if (note) { setMsg(note); setTimeout(() => setMsg(null), 2000) }
  }
  const err = (e: unknown) => setMsg((e as Error).message)

  const save = useMutation({
    mutationFn: () => {
      const vars: Record<string, string> = {}
      for (const r of rows) { const k = r.key.trim(); if (k) vars[k] = r.value }
      return api.globalEnv.setVars(scope || null, vars)
    },
    onSuccess: d => done(d, '✓ Saved'), onError: err,
  })
  const create = useMutation({
    mutationFn: (name: string) => api.globalEnv.create(name),
    onSuccess: (d, name) => { done(d, `✓ Environment ${name} created`); setNewName(null); setScope(name) }, onError: err,
  })
  const rename = useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) => api.globalEnv.rename(from, to),
    onSuccess: (d, v) => { done(d, `✓ Renamed to ${v.to}`); setRenaming(null); setScope(v.to) }, onError: err,
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.globalEnv.remove(name),
    onSuccess: d => { done(d, '✓ Deleted (a copy is kept in ~/.hydra/_backups)'); setScope(COMMON) }, onError: err,
  })

  const badKeys = rows.filter(r => r.key.trim() && !VAR_RE.test(r.key.trim()))
  const dupKeys = rows.map(r => r.key.trim()).filter((k, i, a) => k && a.indexOf(k) !== i)
  const canSave = dirty && !badKeys.length && !dupKeys.length && !save.isPending

  const edit = (id: number, patch: Partial<Row>) => { setRows(rs => rs.map(r => r.id === id ? { ...r, ...patch } : r)); setDirty(true) }
  const choose = (s: string) => {
    if (dirty && !window.confirm('Discard the unsaved changes?')) return
    setScope(s)
  }

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
  }
  const pill = (active: boolean): React.CSSProperties => ({
    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 12px', fontSize: 12, fontWeight: 600,
    borderRadius: 7, border: 'none', cursor: 'pointer',
    background: active ? 'var(--primary)' : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })
  const iconBtn: React.CSSProperties = {
    width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6,
    border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer',
  }

  return (
    <section id="environments" data-testid="environments-manager"
      style={{ margin: '22px 0 4px', padding: 14, borderRadius: 10, border: '1px solid var(--bg-border)' }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>Environments</div>
      <p className="text-slate-400 text-xs" style={{ marginBottom: 12, lineHeight: 1.5 }}>
        Environment variables shared by every project on this machine, saved in{' '}
        <code>{q.data?.home ?? '~/.hydra'}</code> (not in this browser). Choose the active environment on the
        project page or in the editor; runs then load the common variables, then those of the environment.
        Use them as <code>{'${ENV:NAME}'}</code>. Secrets go in Project settings › Secrets.
      </p>

      {q.isLoading && <div className="text-xs" style={{ color: 'var(--text-muted)' }}><Loader2 size={12} /> Loading…</div>}
      {q.isError && <div className="text-xs" style={{ color: 'var(--error)' }}>{(q.error as Error).message}</div>}

      {q.data && (<>
        {/* Onglets : Common + environnements */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4, padding: 3, borderRadius: 9, background: 'var(--bg-hover)', marginBottom: 10 }}>
          <button type="button" style={pill(scope === COMMON)} onClick={() => choose(COMMON)}
            title="Variables of every environment (~/.hydra/env)">Common</button>
          {envs.map(n => renaming === n ? (
            <RenameBox key={n} initial={n} busy={rename.isPending}
              onCancel={() => setRenaming(null)} onOk={to => rename.mutate({ from: n, to })} />
          ) : (
            <button key={n} type="button" style={pill(scope === n)} onClick={() => choose(n)}
              title={`~/.hydra/env.${n}`}>{n}</button>
          ))}
          {newName === null ? (
            <button type="button" style={{ ...pill(false), color: 'var(--primary)' }} onClick={() => setNewName('')}
              data-testid="env-new"><Plus size={12} /> New environment</button>
          ) : (
            <RenameBox initial="" placeholder="prod" busy={create.isPending}
              onCancel={() => setNewName(null)} onOk={n => create.mutate(n)} />
          )}
        </div>

        {/* Actions de l'environnement sélectionné */}
        {scope !== COMMON && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <button type="button" className="btn-secondary text-xs" onClick={() => setRenaming(scope)}>
              <Pencil size={12} /> Rename
            </button>
            <button type="button" className="btn-secondary text-xs" style={{ color: 'var(--error)' }}
              onClick={() => {
                if (window.confirm(`Delete the environment '${scope}' and its global variables? `
                  + 'A copy is kept in ~/.hydra/_backups. Parameter values and secrets of projects are not touched '
                  + '(delete them in Project settings or with hdrctl env delete --project).')) remove.mutate(scope)
              }}>
              <Trash2 size={12} /> Delete
            </button>
            <span className="text-xs" style={{ color: 'var(--text-muted)', alignSelf: 'center', fontFamily: 'monospace' }}>{current?.file}</span>
          </div>
        )}
        {scope === COMMON && (
          <div className="text-xs" style={{ color: 'var(--text-muted)', marginBottom: 8, fontFamily: 'monospace' }}>{current?.file}</div>
        )}

        {/* Variables */}
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              {['Variable', 'Value', ''].map(h => (
                <th key={h} style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'left', padding: '0 4px 4px' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id}>
                <td style={{ padding: 3, width: '38%' }}>
                  <input style={{ ...input, width: '100%', fontFamily: 'monospace',
                    borderColor: r.key.trim() && !VAR_RE.test(r.key.trim()) ? 'var(--error)' : 'var(--bg-border)' }}
                    value={r.key} placeholder="DB_HOST" aria-label="Variable name"
                    onChange={e => edit(r.id, { key: e.target.value })} />
                </td>
                <td style={{ padding: 3 }}>
                  <input style={{ ...input, width: '100%' }} value={r.value} placeholder="value" aria-label="Variable value"
                    onChange={e => edit(r.id, { value: e.target.value })} />
                </td>
                <td style={{ padding: 3, width: 28 }}>
                  <button type="button" style={iconBtn} title="Remove"
                    onClick={() => { setRows(rs => rs.filter(x => x.id !== r.id)); setDirty(true) }}><X size={12} /></button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={3} style={{ padding: 8, fontSize: 12, color: 'var(--text-muted)' }}>No variable.</td></tr>
            )}
          </tbody>
        </table>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn-secondary text-xs" data-testid="env-add-var"
            onClick={() => { setRows(rs => [...rs, { id: _seq++, key: '', value: '' }]); setDirty(true) }}>
            <Plus size={12} /> Add variable
          </button>
          <button type="button" className="btn-primary text-xs" disabled={!canSave} onClick={() => save.mutate()}
            data-testid="env-save" style={{ opacity: canSave ? 1 : 0.5 }}>
            {save.isPending ? <Loader2 size={12} /> : <Save size={12} />} Save {scope === COMMON ? 'common variables' : scope}
          </button>
          {badKeys.length > 0 && <span className="text-xs" style={{ color: 'var(--error)' }}>Names: letters, digits and _ (not starting with a digit).</span>}
          {dupKeys.length > 0 && <span className="text-xs" style={{ color: 'var(--error)' }}>Duplicate: {dupKeys[0]}</span>}
          {msg && <span className="text-xs" style={{ color: msg.startsWith('✓') ? 'var(--primary)' : 'var(--error)' }}>{msg}</span>}
        </div>
      </>)}
    </section>
  )
}

/** Saisie d'un nom d'environnement (création ou renommage). */
function RenameBox({ initial, placeholder, busy, onOk, onCancel }: {
  initial: string; placeholder?: string; busy: boolean; onOk: (v: string) => void; onCancel: () => void
}) {
  const [v, setV] = useState(initial)
  const ok = NAME_RE.test(v.trim()) && v.trim() !== initial
  return (
    <form style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}
      onSubmit={e => { e.preventDefault(); if (ok) onOk(v.trim()) }}>
      <input autoFocus value={v} placeholder={placeholder} aria-label="Environment name"
        onChange={e => setV(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') onCancel() }}
        style={{ width: 110, boxSizing: 'border-box', background: 'var(--bg-input)', border: `1px solid ${v && !NAME_RE.test(v.trim()) ? 'var(--error)' : 'var(--bg-border)'}`,
          borderRadius: 6, padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12 }} />
      <button type="submit" disabled={!ok || busy} title="OK" style={{ border: 'none', background: 'transparent', color: 'var(--primary)', cursor: 'pointer', opacity: ok ? 1 : 0.4 }}>
        {busy ? <Loader2 size={13} /> : <Check size={13} />}
      </button>
      <button type="button" onClick={onCancel} title="Cancel" style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}><X size={13} /></button>
    </form>
  )
}
