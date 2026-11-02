/**
 * ParametersPanel — Project settings › Parameters.
 *
 * Une ligne par paramètre, une colonne par environnement :
 *   name | type | default | <env 1> | <env 2> … | required | description
 * « default » écrit parameters.yaml ; chaque colonne d'environnement écrit
 * environments/<env>.yaml. Une cellule vide hérite de la valeur par défaut.
 * Les environnements proposés sont ceux du projet et ceux de Global settings ›
 * Environments. Mêmes fichiers que `hdrctl param` et que le moteur à l'exécution.
 */
import { useEffect, useMemo, useState } from 'react'
import { Plus, X, Save, Loader2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useActiveEnv } from '@/lib/activeEnv'

const TYPES = ['string', 'int', 'float', 'bool', 'json', 'any']
const NAME_RE = /^[A-Za-z0-9_.-]+$/

interface Decl { _id: number; name: string; type: string; default: string; required: boolean; description: string }
let _seq = 1
const nid = () => _seq++

/** Texte saisi -> valeur typée écrite dans le YAML (le moteur reconvertit de toute façon). */
export function typedValue(raw: string, type: string): unknown {
  const s = raw.trim()
  if (type === 'int' && /^-?\d+$/.test(s)) return Number(s)
  if (type === 'float' && s !== '' && !Number.isNaN(Number(s))) return Number(s)
  if (type === 'bool' && /^(true|false)$/i.test(s)) return s.toLowerCase() === 'true'
  if (type === 'json') { try { return JSON.parse(s) } catch { return raw } }
  return raw
}
const shown = (v: unknown) => v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v)

interface Props { projectId: string; accent?: string }

export default function ParametersPanel({ projectId, accent = 'var(--primary)' }: Props) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['parameters', projectId],
    queryFn: () => api.parameters.get(projectId),
    enabled: Boolean(projectId),
  })
  const names = useQuery({ queryKey: ['env-names', projectId], queryFn: () => api.globalEnv.names(projectId) })
  const [activeEnv] = useActiveEnv(projectId)

  const [decls, setDecls] = useState<Decl[]>([])
  const [values, setValues] = useState<Record<string, Record<string, string>>>({})
  const [extraEnvs, setExtraEnvs] = useState<string[]>([])
  const [dirty, setDirty] = useState(false)

  const projectEnvs = Object.keys(data?.environments ?? {})
  const envs = useMemo(() => Array.from(new Set([
    ...projectEnvs, ...(names.data ?? []).map(n => n.name), ...extraEnvs,
  ])).sort(), [projectEnvs.join('|'), names.data, extraEnvs])     // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!data) return
    setDecls(Object.entries(data.declarations || {}).map(([name, spec]) => {
      const s = (spec && typeof spec === 'object' ? spec : { default: spec }) as Record<string, unknown>
      return { _id: nid(), name, type: String(s.type ?? 'string'), default: shown(s.default),
        required: Boolean(s.required), description: String(s.description ?? '') }
    }))
    const v: Record<string, Record<string, string>> = {}
    for (const [en, vals] of Object.entries(data.environments || {})) {
      v[en] = {}
      for (const [k, val] of Object.entries((vals ?? {}) as Record<string, unknown>)) v[en][k] = shown(val)
    }
    setValues(v)
    setDirty(false)
  }, [data])

  const save = useMutation({
    mutationFn: () => {
      const declarations: Record<string, Record<string, unknown>> = {}
      for (const r of decls) {
        const n = r.name.trim(); if (!n) continue
        const spec: Record<string, unknown> = { type: r.type }
        if (r.default !== '') spec.default = typedValue(r.default, r.type)
        if (r.required) spec.required = true
        if (r.description.trim()) spec.description = r.description.trim()
        declarations[n] = spec
      }
      const environments: Record<string, Record<string, unknown>> = {}
      for (const en of envs) {
        const out: Record<string, unknown> = {}
        for (const r of decls) {
          const n = r.name.trim(); if (!n) continue
          const val = values[en]?.[n]
          if (val !== undefined && val !== '') out[n] = typedValue(val, r.type)
        }
        // N'écrit environments/<env>.yaml que s'il existe déjà ou s'il a des valeurs
        if (projectEnvs.includes(en) || Object.keys(out).length) environments[en] = out
      }
      return api.parameters.save({ project_id: projectId, declarations, environments })
    },
    onSuccess: () => {
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['parameters', projectId] })
      qc.invalidateQueries({ queryKey: ['env-names'] })
    },
  })

  const updateDecl = (id: number, patch: Partial<Decl>) => { setDecls(rows => rows.map(r => r._id === id ? { ...r, ...patch } : r)); setDirty(true) }
  const addDecl = () => { setDecls(rows => [...rows, { _id: nid(), name: '', type: 'string', default: '', required: false, description: '' }]); setDirty(true) }
  const removeDecl = (id: number) => { setDecls(rows => rows.filter(r => r._id !== id)); setDirty(true) }
  const setVal = (env: string, name: string, val: string) => {
    setValues(v => ({ ...v, [env]: { ...(v[env] ?? {}), [name]: val } })); setDirty(true)
  }
  const addEnv = () => {
    const name = (window.prompt('Environment for this project only (e.g. staging). To share it with every project, create it in Global settings › Environments.') || '').trim()
    if (!name) return
    if (!/^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(name)) { window.alert('Use letters, digits, _ or -'); return }
    if (!envs.includes(name)) setExtraEnvs(e => [...e, name])
  }

  const bad = decls.filter(r => r.name.trim() && !NAME_RE.test(r.name.trim()))
  const dup = decls.map(r => r.name.trim()).filter((n, i, a) => n && a.indexOf(n) !== i)

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
  }
  const head: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', padding: '0 6px 4px', whiteSpace: 'nowrap' }

  if (!projectId) return <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)' }}>Open a project to edit parameters.</div>
  if (isLoading) return <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 6, alignItems: 'center' }}><Loader2 size={13} /> Loading…</div>
  if (error) return <div style={{ padding: 12, fontSize: 12, color: 'var(--error)' }}>{(error as Error).message}</div>

  return (
    <div data-testid="parameters-panel" style={{ overflow: 'auto', padding: '4px 4px 16px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.5 }}>
        <b>Default</b> is written to <code>parameters.yaml</code>, each environment column to{' '}
        <code>environments/&lt;env&gt;.yaml</code>. An empty cell inherits the default. Use a parameter as{' '}
        <code>{'{{ param:name }}'}</code> in any field, or <code>params["name"]</code> in a Script node.
      </div>

      <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: '100%' }}>
        <thead>
          <tr>
            <th style={head}>Name</th>
            <th style={head}>Type</th>
            <th style={head}>Default</th>
            {envs.map(en => (
              <th key={en} style={{ ...head, color: en === activeEnv ? accent : head.color }}
                title={en === activeEnv ? 'Active environment' : `environments/${en}.yaml`}>
                {en}{en === activeEnv ? ' ●' : ''}
              </th>
            ))}
            <th style={head}>
              <button type="button" onClick={addEnv} title="Add an environment column for this project"
                style={{ border: 'none', background: 'transparent', color: accent, cursor: 'pointer', padding: 0, display: 'inline-flex' }}>
                <Plus size={12} />
              </button>
            </th>
            <th style={head}>Req</th>
            <th style={head}>Description</th>
            <th style={{ width: 28 }} />
          </tr>
        </thead>
        <tbody>
          {decls.map(r => {
            const n = r.name.trim()
            return (
              <tr key={r._id}>
                <td style={{ padding: 3 }}>
                  <input style={{ ...input, width: 150, fontFamily: 'monospace', borderColor: n && !NAME_RE.test(n) ? 'var(--error)' : 'var(--bg-border)' }}
                    value={r.name} onChange={e => updateDecl(r._id, { name: e.target.value })} placeholder="batch_size" aria-label="Parameter name" />
                </td>
                <td style={{ padding: 3 }}>
                  <select style={{ ...input, width: 84, cursor: 'pointer' }} value={r.type} onChange={e => updateDecl(r._id, { type: e.target.value })}>
                    {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td style={{ padding: 3 }}>
                  <input style={{ ...input, width: 120 }} value={r.default} onChange={e => updateDecl(r._id, { default: e.target.value })} placeholder="1000" aria-label="Default value" />
                </td>
                {envs.map(en => (
                  <td key={en} style={{ padding: 3 }}>
                    <input style={{ ...input, width: 120, borderColor: en === activeEnv ? accent : 'var(--bg-border)' }}
                      value={values[en]?.[n] ?? ''} disabled={!n}
                      onChange={e => setVal(en, n, e.target.value)}
                      placeholder={r.default ? `(${r.default})` : '(default)'} aria-label={`Value for ${en}`} />
                  </td>
                ))}
                <td />
                <td style={{ padding: 3, textAlign: 'center' }}>
                  <input type="checkbox" checked={r.required} onChange={e => updateDecl(r._id, { required: e.target.checked })} aria-label="Required" />
                </td>
                <td style={{ padding: 3 }}>
                  <input style={{ ...input, width: 200 }} value={r.description} onChange={e => updateDecl(r._id, { description: e.target.value })} placeholder="optional" aria-label="Description" />
                </td>
                <td style={{ padding: 3 }}>
                  <button type="button" onClick={() => removeDecl(r._id)} title="Remove"
                    style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                    <X size={12} />
                  </button>
                </td>
              </tr>
            )
          })}
          {decls.length === 0 && <tr><td colSpan={envs.length + 7} style={{ padding: 10, color: 'var(--text-muted)' }}>No parameter yet.</td></tr>}
        </tbody>
      </table>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        <button type="button" onClick={addDecl} data-testid="param-add"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}>
          <Plus size={13} /> Add parameter
        </button>
        <button type="button" onClick={() => save.mutate()} disabled={save.isPending || !dirty || bad.length > 0 || dup.length > 0}
          data-testid="param-save"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: 'none', background: accent, color: '#fff', cursor: 'pointer', opacity: (!dirty || bad.length || dup.length) ? 0.5 : 1 }}>
          {save.isPending ? <Loader2 size={13} /> : <Save size={13} />} Save
        </button>
        {bad.length > 0 && <span style={{ fontSize: 11, color: 'var(--error)' }}>Names: letters, digits, '.', '_' or '-'.</span>}
        {dup.length > 0 && <span style={{ fontSize: 11, color: 'var(--error)' }}>Duplicate: {dup[0]}</span>}
        {save.isError && <span style={{ fontSize: 11, color: 'var(--error)' }}>{(save.error as Error)?.message}</span>}
        {save.isSuccess && !dirty && <span style={{ fontSize: 11, color: 'var(--success, #22c55e)' }}>✓ Saved</span>}
      </div>
    </div>
  )
}
