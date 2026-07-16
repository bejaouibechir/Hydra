/**
 * AggregationBuilder — éditeur en lignes pour le nœud aggregate.
 * Une ligne = une agrégation (Output name, Function, Source column).
 * Génère automatiquement le JSON {out: {func, col}} attendu par le moteur.
 * Un basculeur "JSON" permet l'édition brute (round-trip garanti).
 */
import { useState } from 'react'
import { Plus, X } from 'lucide-react'

const FUNCS = ['sum', 'avg', 'count', 'mean', 'min', 'max', 'first', 'last']

interface Row { _id: number; out: string; func: string; col: string }

let _seq = 1
const nid = () => _seq++

function parse(json: string): Row[] {
  try {
    const obj = JSON.parse(json && json.trim() ? json : '{}')
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return []
    return Object.entries(obj).map(([out, spec]: [string, any]) => {
      if (spec && typeof spec === 'object') return { _id: nid(), out, func: String(spec.func ?? 'sum'), col: String(spec.col ?? '') }
      if (typeof spec === 'string')          return { _id: nid(), out, func: spec, col: out }
      return { _id: nid(), out, func: 'sum', col: '' }
    })
  } catch { return [] }
}

function serialize(rows: Row[]): string {
  const obj: Record<string, { func: string; col: string }> = {}
  for (const r of rows) {
    const out = r.out.trim()
    if (!out) continue
    obj[out] = { func: r.func, col: r.col.trim() || out }
  }
  return JSON.stringify(obj)
}

interface Props {
  value: string
  accent?: string
  onChange: (json: string) => void
}

export default function AggregationBuilder({ value, accent = 'var(--primary)', onChange }: Props) {
  const [advanced, setAdvanced] = useState(false)
  const [rows, setRows] = useState<Row[]>(() => {
    const r = parse(value)
    return r.length ? r : [{ _id: nid(), out: '', func: 'sum', col: '' }]
  })

  const sync = (next: Row[]) => { setRows(next); onChange(serialize(next)) }
  const update = (id: number, patch: Partial<Row>) => sync(rows.map(r => r._id === id ? { ...r, ...patch } : r))
  const add = () => sync([...rows, { _id: nid(), out: '', func: 'sum', col: '' }])
  const remove = (id: number) => { const next = rows.filter(r => r._id !== id); sync(next.length ? next : [{ _id: nid(), out: '', func: 'sum', col: '' }]) }

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 8, padding: '7px 10px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  }
  const head: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }
  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', fontSize: 11, fontWeight: 600, cursor: 'pointer', borderRadius: 6, border: 'none',
    background: active ? accent : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })

  return (
    <div>
      {/* Basculeur Builder / JSON */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, marginBottom: 8 }}>
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-hover)', borderRadius: 8, padding: 3 }}>
          <button type="button" style={tabBtn(!advanced)} onClick={() => setAdvanced(false)}>Builder</button>
          <button type="button" style={tabBtn(advanced)}
            onClick={() => { onChange(serialize(rows)); setAdvanced(true) }}>JSON</button>
        </div>
      </div>

      {advanced ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          onBlur={() => setRows(() => { const r = parse(value); return r.length ? r : [{ _id: nid(), out: '', func: 'sum', col: '' }] })}
          rows={4}
          placeholder='{"total": {"func": "sum", "col": "amount"}}'
          style={{ ...input, display: 'block', width: '100%', resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
        />
      ) : (
        <div>
          {/* En-têtes de colonnes */}
          <div style={{ display: 'flex', gap: 6, padding: '0 30px 4px 0' }}>
            <span style={{ ...head, flex: 1.2 }}>Output name</span>
            <span style={{ ...head, width: 104 }}>Function</span>
            <span style={{ ...head, flex: 1 }}>Source column</span>
          </div>

          {/* Lignes */}
          {rows.map(r => (
            <div key={r._id} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
              <input
                style={{ ...input, flex: 1.2, minWidth: 0 }}
                value={r.out}
                onChange={e => update(r._id, { out: e.target.value })}
                placeholder="total_amount"
              />
              <select
                style={{ ...input, width: 104, cursor: 'pointer' }}
                value={r.func}
                onChange={e => update(r._id, { func: e.target.value })}
              >
                {FUNCS.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              <input
                style={{ ...input, flex: 1, minWidth: 0 }}
                value={r.col}
                onChange={e => update(r._id, { col: e.target.value })}
                placeholder="amount"
              />
              <button
                type="button"
                onClick={() => remove(r._id)}
                title="Remove"
                style={{ flexShrink: 0, width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={13} />
              </button>
            </div>
          ))}

          {/* Ajouter */}
          <button
            type="button"
            onClick={add}
            style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}
          >
            <Plus size={13} /> Add aggregation
          </button>
        </div>
      )}
    </div>
  )
}
