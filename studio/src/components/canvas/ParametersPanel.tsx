/**
 * ParametersPanel — onglet « Parameters » du volet bas (authoring).
 *
 * Édite les DÉCLARATIONS (name/type/default/required/description) et les VALEURS
 * par ENVIRONNEMENT. Persiste via l'API : parameters.yaml + environments/<env>.yaml
 * à la racine du projet (mêmes fichiers que le runner résout à l'exécution).
 * Colonne « Effective » = valeur de l'env actif, sinon défaut (modèle Postman).
 */
import { useEffect, useState } from 'react'
import { Plus, X, Save, Loader2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

const TYPES = ['string', 'int', 'float', 'bool', 'json', 'any']

interface Decl { _id: number; name: string; type: string; default: string; required: boolean; description: string }
let _seq = 1
const nid = () => _seq++

interface Props { projectId: string; accent?: string }

export default function ParametersPanel({ projectId, accent = 'var(--primary)' }: Props) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['parameters', projectId],
    queryFn: () => api.parameters.get(projectId),
    enabled: Boolean(projectId),
  })

  const [decls, setDecls] = useState<Decl[]>([])
  const [envs, setEnvs] = useState<string[]>(['dev'])
  const [activeEnv, setActiveEnv] = useState('dev')
  const [values, setValues] = useState<Record<string, Record<string, string>>>({})

  useEffect(() => {
    if (!data) return
    const d: Decl[] = Object.entries(data.declarations || {}).map(([name, spec]) => {
      const s = (spec ?? {}) as Record<string, unknown>
      return {
        _id: nid(), name, type: String(s.type ?? 'string'),
        default: s.default != null ? String(s.default) : '',
        required: Boolean(s.required), description: String(s.description ?? ''),
      }
    })
    setDecls(d)
    const envNames = Object.keys(data.environments || {})
    setEnvs(envNames.length ? envNames : ['dev'])
    setActiveEnv(prev => envNames.includes(prev) ? prev : (envNames[0] ?? 'dev'))
    const v: Record<string, Record<string, string>> = {}
    for (const [en, vals] of Object.entries(data.environments || {})) {
      v[en] = {}
      for (const [k, val] of Object.entries((vals ?? {}) as Record<string, unknown>)) v[en][k] = val == null ? '' : String(val)
    }
    setValues(v)
  }, [data])

  const save = useMutation({
    mutationFn: () => {
      const declarations: Record<string, Record<string, unknown>> = {}
      for (const r of decls) {
        const n = r.name.trim(); if (!n) continue
        const spec: Record<string, unknown> = { type: r.type }
        if (r.default !== '') spec.default = r.default
        if (r.required) spec.required = true
        if (r.description.trim()) spec.description = r.description.trim()
        declarations[n] = spec
      }
      const environments: Record<string, Record<string, unknown>> = {}
      for (const en of envs) {
        environments[en] = {}
        for (const r of decls) {
          const n = r.name.trim(); if (!n) continue
          const val = values[en]?.[n]
          if (val !== undefined && val !== '') environments[en][n] = val
        }
      }
      return api.parameters.save({ project_id: projectId, declarations, environments })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['parameters', projectId] }),
  })

  const updateDecl = (id: number, patch: Partial<Decl>) => setDecls(rows => rows.map(r => r._id === id ? { ...r, ...patch } : r))
  const addDecl = () => setDecls(rows => [...rows, { _id: nid(), name: '', type: 'string', default: '', required: false, description: '' }])
  const removeDecl = (id: number) => setDecls(rows => rows.filter(r => r._id !== id))
  const setVal = (name: string, val: string) => setValues(v => ({ ...v, [activeEnv]: { ...(v[activeEnv] ?? {}), [name]: val } }))
  const addEnv = () => {
    const name = (window.prompt('Environment name (e.g. prod)') || '').trim()
    if (!name) return
    if (!envs.includes(name)) setEnvs(e => [...e, name])
    setActiveEnv(name)
  }

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
  }
  const head: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', padding: '0 6px 4px' }
  const envBtn = (active: boolean): React.CSSProperties => ({
    padding: '3px 12px', fontSize: 11, fontWeight: 600, cursor: 'pointer', borderRadius: 6, border: 'none',
    background: active ? accent : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })

  if (!projectId) return <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)' }}>Open a project to edit parameters.</div>
  if (isLoading) return <div style={{ padding: 12, fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 6, alignItems: 'center' }}><Loader2 size={13} /> Loading…</div>

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '4px 4px 16px' }}>
      {/* Barre : env actif + save */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, position: 'sticky', top: 0, background: 'var(--bg-card)', paddingBottom: 6, zIndex: 1 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Environment</span>
        <div style={{ display: 'inline-flex', gap: 4, background: 'var(--bg-hover)', borderRadius: 8, padding: 3 }}>
          {envs.map(en => <button key={en} type="button" style={envBtn(en === activeEnv)} onClick={() => setActiveEnv(en)}>{en}</button>)}
          <button type="button" title="Add environment" onClick={addEnv} style={{ ...envBtn(false), padding: '3px 8px' }}><Plus size={12} /></button>
        </div>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={() => save.mutate()} disabled={save.isPending}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: 'none', background: accent, color: '#fff', cursor: 'pointer' }}>
          {save.isPending ? <Loader2 size={13} /> : <Save size={13} />} Save
        </button>
        {save.isError && <span style={{ fontSize: 11, color: 'var(--error)' }}>{(save.error as Error)?.message}</span>}
        {save.isSuccess && !save.isPending && <span style={{ fontSize: 11, color: 'var(--success, #22c55e)' }}>✓ Saved</span>}
      </div>

      {/* Grille des paramètres */}
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <thead>
          <tr>
            <th style={head}>Name</th>
            <th style={{ ...head, width: 92 }}>Type</th>
            <th style={{ ...head, width: 120 }}>Default</th>
            <th style={{ ...head, width: 140 }}>Value ({activeEnv})</th>
            <th style={{ ...head, width: 120 }}>Effective</th>
            <th style={{ ...head, width: 48 }}>Req</th>
            <th style={head}>Description</th>
            <th style={{ width: 28 }} />
          </tr>
        </thead>
        <tbody>
          {decls.map(r => {
            const eff = (values[activeEnv]?.[r.name.trim()] ?? '') || r.default || '∅'
            return (
              <tr key={r._id}>
                <td style={{ padding: 3 }}><input style={{ ...input, width: '100%' }} value={r.name} onChange={e => updateDecl(r._id, { name: e.target.value })} placeholder="batch_size" /></td>
                <td style={{ padding: 3 }}>
                  <select style={{ ...input, width: 92, cursor: 'pointer' }} value={r.type} onChange={e => updateDecl(r._id, { type: e.target.value })}>
                    {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td style={{ padding: 3 }}><input style={{ ...input, width: 120 }} value={r.default} onChange={e => updateDecl(r._id, { default: e.target.value })} placeholder="1000" /></td>
                <td style={{ padding: 3 }}><input style={{ ...input, width: 140 }} value={values[activeEnv]?.[r.name.trim()] ?? ''} onChange={e => setVal(r.name.trim(), e.target.value)} placeholder="(inherits default)" /></td>
                <td style={{ padding: '3px 6px', color: 'var(--text-secondary)', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{eff}</td>
                <td style={{ padding: 3, textAlign: 'center' }}><input type="checkbox" checked={r.required} onChange={e => updateDecl(r._id, { required: e.target.checked })} /></td>
                <td style={{ padding: 3 }}><input style={{ ...input, width: '100%' }} value={r.description} onChange={e => updateDecl(r._id, { description: e.target.value })} placeholder="optional" /></td>
                <td style={{ padding: 3 }}>
                  <button type="button" onClick={() => removeDecl(r._id)} title="Remove"
                    style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                    <X size={12} />
                  </button>
                </td>
              </tr>
            )
          })}
          {decls.length === 0 && <tr><td colSpan={8} style={{ padding: 10, color: 'var(--text-muted)' }}>No parameter yet.</td></tr>}
        </tbody>
      </table>

      <button type="button" onClick={addDecl}
        style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}>
        <Plus size={13} /> Add parameter
      </button>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
        Reference with <code>{'{{ param:name }}'}</code> in YAML, or <code>params["name"]</code> in a Script node.
      </div>
    </div>
  )
}
