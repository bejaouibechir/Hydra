/**
 * WindowBuilder — éditeur en lignes pour le nœud window.
 * Une ligne = une colonne ajoutée (Output name, Function, Column, Offset, Default).
 * Génère le JSON {out: {func, col?, offset?, default?}} attendu par le moteur
 * (internal/engines/window.py). Basculeur "JSON" pour l'édition brute.
 */
import { useState } from 'react'
import { Plus, X } from 'lucide-react'

export const WINDOW_FUNCS: { group: string; funcs: string[] }[] = [
  { group: 'Rank',            funcs: ['row_number', 'rank', 'dense_rank'] },
  { group: 'Offset',          funcs: ['lag', 'lead'] },
  { group: 'Running',         funcs: ['cumsum', 'cumcount', 'cummin', 'cummax'] },
  { group: 'Whole partition', funcs: ['sum', 'mean', 'min', 'max', 'count', 'first', 'last'] },
]
const NO_COL = new Set(['row_number', 'rank', 'dense_rank'])
const OFFSET = new Set(['lag', 'lead'])

interface Row { _id: number; out: string; func: string; col: string; offset: string; def: string }

let _seq = 1
const nid = () => _seq++
const empty = (): Row => ({ _id: nid(), out: '', func: 'row_number', col: '', offset: '', def: '' })

export function parseWindowColumns(json: string): Row[] {
  try {
    const obj = JSON.parse(json && json.trim() ? json : '{}')
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return []
    return Object.entries(obj).map(([out, spec]: [string, any]) => ({
      _id: nid(), out,
      func: String(spec?.func ?? 'row_number'),
      col: spec?.col != null ? String(spec.col) : '',
      offset: spec?.offset != null ? String(spec.offset) : '',
      def: spec?.default != null ? String(spec.default) : '',
    }))
  } catch { return [] }
}

/** "0" -> 0, "1.5" -> 1.5, "true" -> true, autre -> texte. */
function typed(v: string): unknown {
  const s = v.trim()
  if (/^-?\d+$/.test(s)) return Number(s)
  if (/^-?\d*\.\d+$/.test(s)) return Number(s)
  if (s === 'true' || s === 'false') return s === 'true'
  return v
}

export function serializeWindowColumns(rows: Row[]): string {
  const obj: Record<string, Record<string, unknown>> = {}
  for (const r of rows) {
    const out = r.out.trim()
    if (!out) continue
    const spec: Record<string, unknown> = { func: r.func }
    if (!NO_COL.has(r.func) && r.col.trim()) spec.col = r.col.trim()
    if (OFFSET.has(r.func)) {
      if (r.offset.trim()) spec.offset = Number(r.offset.trim())
      if (r.def.trim() !== '') spec.default = typed(r.def)
    }
    obj[out] = spec
  }
  return JSON.stringify(obj)
}

interface Props {
  value: string
  accent?: string
  onChange: (json: string) => void
}

export default function WindowBuilder({ value, accent = 'var(--primary)', onChange }: Props) {
  const [advanced, setAdvanced] = useState(false)
  const [rows, setRows] = useState<Row[]>(() => {
    const r = parseWindowColumns(value)
    return r.length ? r : [empty()]
  })

  const sync = (next: Row[]) => { setRows(next); onChange(serializeWindowColumns(next)) }
  const update = (id: number, patch: Partial<Row>) => sync(rows.map(r => r._id === id ? { ...r, ...patch } : r))
  const add = () => sync([...rows, empty()])
  const remove = (id: number) => { const next = rows.filter(r => r._id !== id); sync(next.length ? next : [empty()]) }

  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 8, padding: '7px 10px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  }
  const off: React.CSSProperties = { opacity: 0.35, cursor: 'not-allowed' }
  const head: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }
  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', fontSize: 11, fontWeight: 600, cursor: 'pointer', borderRadius: 6, border: 'none',
    background: active ? accent : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4, marginBottom: 8 }}>
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-hover)', borderRadius: 8, padding: 3 }}>
          <button type="button" style={tabBtn(!advanced)} onClick={() => setAdvanced(false)}>Builder</button>
          <button type="button" style={tabBtn(advanced)}
            onClick={() => { onChange(serializeWindowColumns(rows)); setAdvanced(true) }}>JSON</button>
        </div>
      </div>

      {advanced ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          onBlur={() => setRows(() => { const r = parseWindowColumns(value); return r.length ? r : [empty()] })}
          rows={5}
          placeholder='{"order_rank": {"func": "row_number"}, "prev_amount": {"func": "lag", "col": "amount", "default": 0}}'
          style={{ ...input, display: 'block', width: '100%', resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
        />
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 6, padding: '0 30px 4px 0' }}>
            <span style={{ ...head, flex: 1.2 }}>Output name</span>
            <span style={{ ...head, width: 118 }}>Function</span>
            <span style={{ ...head, flex: 1 }}>Column</span>
            <span style={{ ...head, width: 54 }}>Offset</span>
            <span style={{ ...head, width: 64 }}>Default</span>
          </div>

          {rows.map(r => {
            const noCol = NO_COL.has(r.func)
            const noOff = !OFFSET.has(r.func)
            return (
              <div key={r._id} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                <input style={{ ...input, flex: 1.2, minWidth: 0 }} value={r.out}
                  onChange={e => update(r._id, { out: e.target.value })} placeholder="order_rank" />
                <select style={{ ...input, width: 118, cursor: 'pointer' }} value={r.func}
                  onChange={e => update(r._id, { func: e.target.value })}>
                  {WINDOW_FUNCS.map(g => (
                    <optgroup key={g.group} label={g.group}>
                      {g.funcs.map(f => <option key={f} value={f}>{f}</option>)}
                    </optgroup>
                  ))}
                </select>
                <input style={{ ...input, flex: 1, minWidth: 0, ...(noCol ? off : {}) }} value={noCol ? '' : r.col}
                  disabled={noCol} onChange={e => update(r._id, { col: e.target.value })}
                  placeholder={noCol ? '—' : r.func === 'cumcount' ? '(rows)' : 'amount'} />
                <input style={{ ...input, width: 54, ...(noOff ? off : {}) }} value={noOff ? '' : r.offset}
                  disabled={noOff} onChange={e => update(r._id, { offset: e.target.value.replace(/[^0-9]/g, '') })}
                  placeholder={noOff ? '—' : '1'} />
                <input style={{ ...input, width: 64, ...(noOff ? off : {}) }} value={noOff ? '' : r.def}
                  disabled={noOff} onChange={e => update(r._id, { def: e.target.value })}
                  placeholder={noOff ? '—' : 'null'} />
                <button type="button" onClick={() => remove(r._id)} title="Remove"
                  style={{ flexShrink: 0, width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                  <X size={13} />
                </button>
              </div>
            )
          })}

          <button type="button" onClick={add}
            style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}>
            <Plus size={13} /> Add column
          </button>
          <span style={{ display: 'block', marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
            Rank, offset and running functions need an order. Rows keep their input order; only columns are added.
          </span>
        </div>
      )}
    </div>
  )
}
