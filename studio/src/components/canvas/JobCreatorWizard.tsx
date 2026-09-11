/**
 * JobCreatorWizard — Formulaire de création d'un job Hydra depuis le Studio.
 * Appelle POST /api/jobs/scaffold pour générer les 4 fichiers YAML automatiquement.
 */
import { useState, useCallback } from 'react'
import { Plus, Trash2, Loader2, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Transform {
  id:     number
  op:     string
  params: Record<string, string>
}

interface Props {
  defaultJobName?: string
  onCreated: (jobPath: string) => void
  onCancel:  () => void
}

// ── Constantes ────────────────────────────────────────────────────────────────

const FILE_TYPES = ['csv', 'json', 'parquet']
const DEST_MODES = ['replace', 'append']

const TRANSFORM_OPS = [
  { op: 'filter',  label: 'Filter',  hint: 'Expression Pandas ex: age > 18' },
  { op: 'select',  label: 'Select',  hint: 'Columns to keep, e.g. id, name, email' },
  { op: 'rename',  label: 'Rename',  hint: 'JSON {"old": "new"}' },
  { op: 'cast',    label: 'Cast',    hint: 'JSON {"price": "float", "quantity": "int"}' },
  { op: 'derive',  label: 'Derive',  hint: 'New calculated column' },
  { op: 'sort',    label: 'Sort',    hint: 'Columns to sort by, e.g. name, age' },
]

// ── Helpers styles ────────────────────────────────────────────────────────────

const input: React.CSSProperties = {
  display: 'block', width: '100%', boxSizing: 'border-box',
  background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
  borderRadius: 8, padding: '7px 11px', color: 'var(--text-primary)',
  fontSize: 12, outline: 'none', marginTop: 5,
}

const label12: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
  textTransform: 'uppercase', letterSpacing: '0.05em',
}

const section: React.CSSProperties = {
  background: 'var(--bg-hover)', borderRadius: 10,
  padding: '12px 14px', marginBottom: 12,
}

let _tid = 1

// ── Composant ─────────────────────────────────────────────────────────────────

export default function JobCreatorWizard({ defaultJobName = '', onCreated, onCancel }: Props) {
  const [jobName,   setJobName]   = useState(defaultJobName)
  const [baseDir,   setBaseDir]   = useState('')
  const [srcType,   setSrcType]   = useState('csv')
  const [srcPath,   setSrcPath]   = useState('')
  const [transforms, setTransforms] = useState<Transform[]>([])
  const [destType,  setDestType]  = useState('csv')
  const [destPath,  setDestPath]  = useState('')
  const [destMode,  setDestMode]  = useState('replace')
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)

  // ── Transformations ────────────────────────────────────────────────────────

  const addTransform = () => {
    setTransforms(prev => [...prev, { id: _tid++, op: 'filter', params: { expr: '' } }])
  }

  const removeTransform = (id: number) => {
    setTransforms(prev => prev.filter(t => t.id !== id))
  }

  const updateTransformOp = (id: number, op: string) => {
    setTransforms(prev => prev.map(t => t.id === id
      ? { ...t, op, params: defaultParams(op) } : t
    ))
  }

  const updateTransformParam = (id: number, key: string, val: string) => {
    setTransforms(prev => prev.map(t => t.id === id
      ? { ...t, params: { ...t.params, [key]: val } } : t
    ))
  }

  function defaultParams(op: string): Record<string, string> {
    switch (op) {
      case 'filter': return { expr: '' }
      case 'select': return { columns: '' }
      case 'rename': return { mapping: '{}' }
      case 'cast':   return { mapping: '{}' }
      case 'derive': return { column: '', expr: '' }
      case 'sort':   return { by: '', ascending: 'true' }
      default:       return {}
    }
  }

  // ── Soumission ─────────────────────────────────────────────────────────────

  const handleCreate = useCallback(async () => {
    if (!jobName.trim())   { setError('Job name is required'); return }
    if (!baseDir.trim())   { setError('Base directory is required'); return }
    if (!srcPath.trim())   { setError('Source path is required'); return }
    if (!destPath.trim())  { setError('Destination path is required'); return }

    setLoading(true); setError(null)

    try {
      // Convertir les params de transforms en types attendus par le backend
      const builtTransforms = transforms.map(t => ({
        op: t.op,
        params: buildParams(t.op, t.params),
      }))

      const res = await api.scaffold.job({
        job_name:        jobName.trim(),
        base_dir:        baseDir.trim(),
        source_type:     srcType,
        source_path:     srcPath.trim(),
        transformations: builtTransforms,
        dest_type:       destType,
        dest_path:       destPath.trim(),
        dest_mode:       destMode,
      })

      onCreated(res.job_path)
    } catch (e: any) {
      setError(e?.message ?? 'An error occurred while creating the job')
    } finally {
      setLoading(false)
    }
  }, [jobName, baseDir, srcType, srcPath, transforms, destType, destPath, destMode, onCreated])

  function buildParams(op: string, raw: Record<string, string>): Record<string, unknown> {
    switch (op) {
      case 'filter': return { expr: raw.expr }
      case 'select': return { columns: raw.columns.split(',').map(s => s.trim()).filter(Boolean) }
      case 'rename':
      case 'cast':   try { return { mapping: JSON.parse(raw.mapping || '{}') } } catch { return { mapping: {} } }
      case 'derive': return { column: raw.column, expr: raw.expr }
      case 'sort':   return { by: raw.by.split(',').map(s => s.trim()).filter(Boolean), ascending: raw.ascending === 'true' }
      default:       return raw
    }
  }

  // ── Render params d'une transformation ────────────────────────────────────

  function renderTransformParams(t: Transform) {
    const hint = TRANSFORM_OPS.find(x => x.op === t.op)?.hint ?? ''
    switch (t.op) {
      case 'filter':
        return <input style={input} placeholder={hint} value={t.params.expr ?? ''}
          onChange={e => updateTransformParam(t.id, 'expr', e.target.value)} />
      case 'select':
        return <input style={input} placeholder={hint} value={t.params.columns ?? ''}
          onChange={e => updateTransformParam(t.id, 'columns', e.target.value)} />
      case 'rename':
      case 'cast':
        return <input style={input} placeholder={hint} value={t.params.mapping ?? '{}'}
          onChange={e => updateTransformParam(t.id, 'mapping', e.target.value)} />
      case 'derive':
        return (
          <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
            <input style={{ ...input, marginTop: 0, width: '35%' }} placeholder="column name"
              value={t.params.column ?? ''} onChange={e => updateTransformParam(t.id, 'column', e.target.value)} />
            <input style={{ ...input, marginTop: 0, flex: 1 }} placeholder="price * quantity"
              value={t.params.expr ?? ''} onChange={e => updateTransformParam(t.id, 'expr', e.target.value)} />
          </div>
        )
      case 'sort':
        return (
          <div style={{ display: 'flex', gap: 6, marginTop: 5 }}>
            <input style={{ ...input, marginTop: 0, flex: 1 }} placeholder="col1, col2"
              value={t.params.by ?? ''} onChange={e => updateTransformParam(t.id, 'by', e.target.value)} />
            <select style={{ ...input, marginTop: 0, width: 100 }}
              value={t.params.ascending ?? 'true'}
              onChange={e => updateTransformParam(t.id, 'ascending', e.target.value)}>
              <option value="true">ASC</option>
              <option value="false">DESC</option>
            </select>
          </div>
        )
      default: return null
    }
  }

  // ── JSX ───────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Job identity */}
      <div style={section}>
        <p style={{ ...label12, marginBottom: 10 }}>Job identity</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: 8 }}>
          <label>
            <span style={label12}>Name <span style={{ color: 'var(--error)' }}>*</span></span>
            <input style={input} placeholder="preparer_sources"
              value={jobName} onChange={e => setJobName(e.target.value.replace(/\s+/g, '_'))} />
          </label>
          <label>
            <span style={label12}>Base directory <span style={{ color: 'var(--error)' }}>*</span></span>
            <input style={input} placeholder="D:\my-project\jobs"
              value={baseDir} onChange={e => setBaseDir(e.target.value)} />
          </label>
        </div>
      </div>

      {/* Source */}
      <div style={section}>
        <p style={{ ...label12, marginBottom: 10, color: 'var(--success)' }}>Source</p>
        <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: 8 }}>
          <label>
            <span style={label12}>Type</span>
            <select style={input} value={srcType} onChange={e => setSrcType(e.target.value)}>
              {FILE_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label>
            <span style={label12}>File path <span style={{ color: 'var(--error)' }}>*</span></span>
            <input style={input} placeholder="D:\my-project\data\input\file.csv"
              value={srcPath} onChange={e => setSrcPath(e.target.value)} />
          </label>
        </div>
      </div>

      {/* Transformations */}
      <div style={section}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <p style={{ ...label12, margin: 0, color: 'var(--primary)' }}>Transformations</p>
          <button onClick={addTransform}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600,
              background: 'var(--primary-subtle)', color: 'var(--primary)', border: 'none',
              borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}>
            <Plus size={12} /> Add
          </button>
        </div>

        {transforms.length === 0 && (
          <p style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic', margin: 0 }}>
            No transformations — data passes through unchanged.
          </p>
        )}

        {transforms.map((t, i) => (
          <div key={t.id} style={{
            background: 'var(--bg-card)', borderRadius: 8, padding: '10px 12px',
            marginBottom: i < transforms.length - 1 ? 8 : 0,
            border: '1px solid var(--bg-border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <select
                value={t.op}
                onChange={e => updateTransformOp(t.id, e.target.value)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
                  borderRadius: 6, padding: '4px 8px', color: 'var(--primary)',
                  fontSize: 11, fontWeight: 600, outline: 'none', cursor: 'pointer' }}
              >
                {TRANSFORM_OPS.map(x => <option key={x.op} value={x.op}>{x.label}</option>)}
              </select>
              <div style={{ flex: 1 }}>{renderTransformParams(t)}</div>
              <button onClick={() => removeTransform(t.id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', padding: 4, borderRadius: 4, flexShrink: 0 }}>
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Destination */}
      <div style={{ ...section, marginBottom: 0 }}>
        <p style={{ ...label12, marginBottom: 10, color: 'var(--warning)' }}>Destination</p>
        <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr 100px', gap: 8 }}>
          <label>
            <span style={label12}>Type</span>
            <select style={input} value={destType} onChange={e => setDestType(e.target.value)}>
              {FILE_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label>
            <span style={label12}>File path <span style={{ color: 'var(--error)' }}>*</span></span>
            <input style={input} placeholder="D:\my-project\data\output\result.csv"
              value={destPath} onChange={e => setDestPath(e.target.value)} />
          </label>
          <label>
            <span style={label12}>Mode</span>
            <select style={input} value={destMode} onChange={e => setDestMode(e.target.value)}>
              {DEST_MODES.map(m => <option key={m}>{m}</option>)}
            </select>
          </label>
        </div>
      </div>

      {/* Erreur */}
      {error && (
        <p style={{ fontSize: 12, color: 'var(--error)', marginTop: 10, marginBottom: 0 }}>
          ⚠ {error}
        </p>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button
          onClick={handleCreate}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1,
            justifyContent: 'center', padding: '9px 0', borderRadius: 8,
            background: loading ? 'var(--bg-hover)' : 'var(--primary)',
            color: loading ? 'var(--text-muted)' : '#fff',
            border: 'none', fontSize: 13, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          {loading
            ? <><Loader2 size={14} className="animate-spin" /> Creating…</>
            : <><CheckCircle2 size={14} /> Create job</>}
        </button>
        <button
          onClick={onCancel}
          style={{ padding: '9px 20px', borderRadius: 8, fontSize: 13,
            background: 'var(--bg-hover)', color: 'var(--text-secondary)',
            border: '1px solid var(--bg-border)', cursor: 'pointer' }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
