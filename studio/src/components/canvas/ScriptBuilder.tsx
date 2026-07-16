/**
 * ScriptBuilder — éditeur du nœud transform_script (façon SSIS Script Component).
 *
 * Contrat colonnes input -> output + code Python édité dans CodeMirror 6 avec :
 *  - autocomplétion des colonnes déclarées (inputs/outputs) + helpers (pd, np, math, re)
 *  - coloration syntaxique Python + lint (output jamais affecté)
 *  - menu éditeur : Preview (10 lignes sur échantillon) + Expand (modal large)
 *  - modal : éditeur agrandi avec undo/redo/cut/copy/paste/parse
 *
 * Émet les params du nœud via onChange({ inputs, outputs, code, mode }).
 * inputs = CSV, outputs = JSON string (format attendu par NodeConfigDialog).
 */
import { useMemo, useState } from 'react'
import { Plus, X, Play, Maximize2, Undo2, Redo2, Scissors, Copy, ClipboardPaste, CheckCircle2, Loader2 } from 'lucide-react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { autocompletion, type CompletionContext } from '@codemirror/autocomplete'
import { linter, type Diagnostic } from '@codemirror/lint'
import { oneDark } from '@codemirror/theme-one-dark'
import { undo, redo } from '@codemirror/commands'
import { EditorView } from '@codemirror/view'
import { api } from '@/lib/api'

const OUT_TYPES = ['any', 'int', 'float', 'str', 'bool', 'date', 'datetime']
const HELPERS = ['abs', 'round', 'min', 'max', 'sum', 'len', 'int', 'float', 'str', 'bool',
  'list', 'dict', 'tuple', 'set', 'sorted', 'zip', 'range', 'enumerate', 'map', 'filter',
  'any', 'all', 'pow', 'divmod', 'isinstance']
const NAMESPACES = [
  { label: 'np', detail: 'numpy' },
  { label: 'pd', detail: 'pandas' },
  { label: 'math', detail: 'math module' },
  { label: 're', detail: 'regex module' },
]

interface OutRow { _id: number; name: string; type: string }
let _seq = 1
const nid = () => _seq++

function parseList(v: string): string[] {
  return (v || '').split(',').map(s => s.trim()).filter(Boolean)
}
function parseOutputs(json: string): OutRow[] {
  try {
    const obj = JSON.parse(json && json.trim() ? json : '{}')
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return []
    return Object.entries(obj).map(([name, type]) => ({ _id: nid(), name, type: String(type || 'any') }))
  } catch { return [] }
}
function serializeOutputs(rows: OutRow[]): string {
  const obj: Record<string, string> = {}
  for (const r of rows) { const n = r.name.trim(); if (n) obj[n] = r.type }
  return JSON.stringify(obj)
}
function escapeRe(s: string): string { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') }

interface Props {
  inputs: string
  outputs: string
  code: string
  mode: string
  accent?: string
  columns?: string[]
  onChange: (patch: Record<string, string>) => void
}

interface PreviewState {
  loading: boolean
  columns: string[]
  rows: Record<string, unknown>[]
  error: string | null
  ran: boolean
}

export default function ScriptBuilder({ inputs, outputs, code, mode, accent = 'var(--primary)', columns = [], onChange }: Props) {
  const inputCols = parseList(inputs)
  const [outRows, setOutRows] = useState<OutRow[]>(() => {
    const r = parseOutputs(outputs)
    return r.length ? r : [{ _id: nid(), name: '', type: 'float' }]
  })
  const outNames = outRows.map(r => r.name.trim()).filter(Boolean)
  const outputsDict = () => {
    const o: Record<string, string> = {}
    for (const r of outRows) { const n = r.name.trim(); if (n) o[n] = r.type }
    return o
  }

  const syncOut = (next: OutRow[]) => { setOutRows(next); onChange({ outputs: serializeOutputs(next) }) }
  const updateOut = (id: number, patch: Partial<OutRow>) => syncOut(outRows.map(r => r._id === id ? { ...r, ...patch } : r))
  const addOut = () => syncOut([...outRows, { _id: nid(), name: '', type: 'float' }])
  const removeOut = (id: number) => { const n = outRows.filter(r => r._id !== id); syncOut(n.length ? n : [{ _id: nid(), name: '', type: 'float' }]) }

  const [draft, setDraft] = useState('')
  const addInput = (raw: string) => {
    const items = parseList(raw)
    if (!items.length) return
    const merged = Array.from(new Set([...inputCols, ...items]))
    onChange({ inputs: merged.join(',') })
    setDraft('')
  }
  const removeInput = (c: string) => onChange({ inputs: inputCols.filter(x => x !== c).join(',') })

  // ── Éditeur (extensions partagées inline + modal) ──
  const extensions = useMemo(() => {
    const completions = (ctx: CompletionContext) => {
      const word = ctx.matchBefore(/[\w]*/)
      if (!word || (word.from === word.to && !ctx.explicit)) return null
      const opts = [
        ...inputCols.map(c => ({ label: c, type: 'variable', detail: 'input column' })),
        ...outNames.map(c => ({ label: c, type: 'variable', detail: 'output column' })),
        ...NAMESPACES.map(n => ({ label: n.label, type: 'namespace', detail: n.detail })),
        ...HELPERS.map(h => ({ label: h, type: 'function' })),
      ]
      return { from: word.from, options: opts }
    }
    const scriptLint = linter(view => {
      const diags: Diagnostic[] = []
      const text = view.state.doc.toString()
      const end = text.length
      for (const out of outNames) {
        const re = new RegExp('(^|\\n)\\s*' + escapeRe(out) + '\\s*[+\\-*/]?=(?!=)')
        if (!re.test(text)) {
          diags.push({ from: 0, to: Math.min(end, 1), severity: 'warning', message: "Output '" + out + "' is never assigned by the code" })
        }
      }
      return diags
    })
    return [python(), autocompletion({ override: [completions] }), scriptLint]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs, outputs])

  // ── Preview (échantillon) ──
  const [sampleRows, setSampleRows] = useState<Record<string, string>[]>([{}])
  const [preview, setPreview] = useState<PreviewState>({ loading: false, columns: [], rows: [], error: null, ran: false })
  const [showPreview, setShowPreview] = useState(false)

  const setCell = (ri: number, col: string, val: string) =>
    setSampleRows(rows => rows.map((r, i) => i === ri ? { ...r, [col]: val } : r))
  const addSampleRow = () => setSampleRows(rows => [...rows, {}])
  const removeSampleRow = (ri: number) => setSampleRows(rows => rows.length > 1 ? rows.filter((_, i) => i !== ri) : rows)

  const buildRows = () => sampleRows.map(r => {
    const o: Record<string, unknown> = {}
    for (const c of inputCols) { const v = r[c]; if (v !== undefined && v !== '') o[c] = v }
    return o
  }).filter(o => Object.keys(o).length > 0)

  const runPreview = async () => {
    setPreview(p => ({ ...p, loading: true, error: null }))
    try {
      const res = await api.transform.scriptPreview({
        inputs: inputCols, outputs: outputsDict(), code,
        mode: mode === 'row' ? 'row' : 'vectorized', rows: buildRows(),
      })
      setPreview({ loading: false, columns: res.columns, rows: res.rows, error: res.error, ran: true })
    } catch (e) {
      setPreview({ loading: false, columns: [], rows: [], error: (e as Error).message ?? String(e), ran: true })
    }
  }

  // ── Modal (Visualize) ──
  const [showModal, setShowModal] = useState(false)
  const [modalView, setModalView] = useState<EditorView | null>(null)
  const [parseMsg, setParseMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const doCopy = (v: EditorView | null) => {
    if (!v) return
    const s = v.state.selection.main
    const t = v.state.sliceDoc(s.from, s.to)
    if (t) navigator.clipboard?.writeText(t).catch(() => {})
  }
  const doCut = (v: EditorView | null) => {
    if (!v) return
    const s = v.state.selection.main
    const t = v.state.sliceDoc(s.from, s.to)
    if (t) { navigator.clipboard?.writeText(t).catch(() => {}); v.dispatch({ changes: { from: s.from, to: s.to, insert: '' } }); v.focus() }
  }
  const doPaste = async (v: EditorView | null) => {
    if (!v) return
    try {
      const t = await navigator.clipboard.readText()
      const s = v.state.selection.main
      v.dispatch({ changes: { from: s.from, to: s.to, insert: t }, selection: { anchor: s.from + t.length } })
      v.focus()
    } catch { /* clipboard indisponible */ }
  }
  const runParse = async () => {
    setParseMsg({ ok: false, text: '…' })
    try {
      const res = await api.transform.scriptPreview({ inputs: inputCols, outputs: outputsDict(), code, mode, rows: [] })
      setParseMsg(res.error ? { ok: false, text: res.error } : { ok: true, text: 'Syntax OK — no errors' })
    } catch (e) {
      setParseMsg({ ok: false, text: (e as Error).message ?? String(e) })
    }
  }

  // ── Styles ──
  const input: React.CSSProperties = {
    boxSizing: 'border-box', background: 'var(--bg-input)', border: '1px solid var(--bg-border)',
    borderRadius: 8, padding: '7px 10px', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  }
  const head: React.CSSProperties = { fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }
  const section: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6, display: 'block' }
  const chip: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 6, fontSize: 12, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-secondary)' }
  const modeBtn = (active: boolean): React.CSSProperties => ({
    padding: '5px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', borderRadius: 6, border: 'none',
    background: active ? accent : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })
  const toolBtn: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
    border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-secondary)', cursor: 'pointer',
  }

  const suggestions = columns.filter(c => !inputCols.includes(c))

  const editor = (height: string, onView?: (v: EditorView) => void) => (
    <CodeMirror
      value={code}
      height={height}
      theme={oneDark}
      extensions={extensions}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: true }}
      onChange={v => onChange({ code: v })}
      onCreateEditor={(view: EditorView) => onView?.(view)}
      placeholder={'# Assign each output column.\n# total = price * quantity'}
    />
  )

  const previewTable = (
    <div style={{ marginTop: 10 }}>
      {preview.loading && <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}><Loader2 size={13} /> Running…</div>}
      {!preview.loading && preview.error && (
        <div style={{ fontSize: 12, color: 'var(--error)', background: 'color-mix(in srgb, var(--error) 12%, transparent)', border: '1px solid var(--error)', borderRadius: 8, padding: '8px 10px', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
          {preview.error}
        </div>
      )}
      {!preview.loading && !preview.error && preview.ran && (
        <div style={{ overflowX: 'auto', border: '1px solid var(--bg-border)', borderRadius: 8 }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
            <thead>
              <tr>{preview.columns.map(c => (
                <th key={c} style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '1px solid var(--bg-border)', color: 'var(--text-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>{c}</th>
              ))}</tr>
            </thead>
            <tbody>
              {preview.rows.length === 0 && <tr><td style={{ padding: '8px 10px', color: 'var(--text-muted)' }} colSpan={Math.max(1, preview.columns.length)}>No rows (add sample data above).</td></tr>}
              {preview.rows.map((r, i) => (
                <tr key={i}>{preview.columns.map(c => (
                  <td key={c} style={{ padding: '6px 10px', borderBottom: '1px solid var(--bg-border)', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{r[c] === null || r[c] === undefined ? '∅' : String(r[c])}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  return (
    <div>
      {/* INPUTS */}
      <div style={{ marginBottom: 16 }}>
        <span style={section}>Input columns</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
          {inputCols.map(c => (
            <span key={c} style={chip}>{c}<X size={12} style={{ cursor: 'pointer' }} onClick={() => removeInput(c)} /></span>
          ))}
          {inputCols.length === 0 && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>No input column yet</span>}
        </div>
        <input
          style={{ ...input, width: '100%' }}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addInput(draft) } }}
          onBlur={() => addInput(draft)}
          placeholder="Type a column name and press Enter (e.g. price)"
        />
        {suggestions.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {suggestions.map(c => (
              <button key={c} type="button" onClick={() => addInput(c)}
                style={{ padding: '2px 8px', borderRadius: 6, fontSize: 11, border: '1px dashed var(--bg-border)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}>+ {c}</button>
            ))}
          </div>
        )}
      </div>

      {/* OUTPUTS */}
      <div style={{ marginBottom: 16 }}>
        <span style={section}>Output columns</span>
        <div style={{ display: 'flex', gap: 6, padding: '0 30px 4px 0' }}>
          <span style={{ ...head, flex: 1.4 }}>Name</span>
          <span style={{ ...head, width: 120 }}>Type</span>
        </div>
        {outRows.map(r => (
          <div key={r._id} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
            <input style={{ ...input, flex: 1.4, minWidth: 0 }} value={r.name} onChange={e => updateOut(r._id, { name: e.target.value })} placeholder="total" />
            <select style={{ ...input, width: 120, cursor: 'pointer' }} value={r.type} onChange={e => updateOut(r._id, { type: e.target.value })}>
              {OUT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <button type="button" onClick={() => removeOut(r._id)} title="Remove"
              style={{ flexShrink: 0, width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-muted)', cursor: 'pointer' }}>
              <X size={13} />
            </button>
          </div>
        ))}
        <button type="button" onClick={addOut}
          style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}>
          <Plus size={13} /> Add output column
        </button>
      </div>

      {/* MODE */}
      <div style={{ marginBottom: 16 }}>
        <span style={section}>Execution mode</span>
        <div style={{ display: 'inline-flex', gap: 4, background: 'var(--bg-hover)', borderRadius: 8, padding: 3 }}>
          <button type="button" style={modeBtn(mode !== 'row')} onClick={() => onChange({ mode: 'vectorized' })}>Vectorized</button>
          <button type="button" style={modeBtn(mode === 'row')} onClick={() => onChange({ mode: 'row' })}>Row-by-row</button>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          {mode === 'row'
            ? 'Each input column is a scalar; runs once per row (SSIS ProcessInputRow style).'
            : 'Each input column is a pandas Series; faster, operate on whole columns.'}
        </div>
      </div>

      {/* CODE + menu éditeur */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
          <span style={{ ...section, marginBottom: 0, flex: 1 }}>Python code</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" style={toolBtn} onClick={() => { setShowPreview(s => !s) }} title="Preview first 10 rows on sample data">
              <Play size={13} /> Preview
            </button>
            <button type="button" style={toolBtn} onClick={() => setShowModal(true)} title="Open large editor">
              <Maximize2 size={13} /> Expand
            </button>
          </div>
        </div>
        <div style={{ border: '1px solid var(--bg-border)', borderRadius: 8, overflow: 'hidden' }}>
          {editor('220px')}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          Available: {inputCols.length ? inputCols.join(', ') : 'declare input columns above'} · np, pd, math, re · Ctrl-Space to autocomplete.
        </div>

        {/* PREVIEW panel */}
        {showPreview && (
          <div style={{ marginTop: 12, border: '1px solid var(--bg-border)', borderRadius: 10, padding: 12, background: 'var(--bg-hover)' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ ...section, marginBottom: 0, flex: 1 }}>Sample input rows</span>
              <button type="button" style={{ ...toolBtn, background: accent, color: '#fff', border: 'none' }} onClick={runPreview} disabled={preview.loading}>
                {preview.loading ? <Loader2 size={13} /> : <Play size={13} />} Run preview
              </button>
            </div>
            {inputCols.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Declare input columns first to fill the sample table.</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr>
                      {inputCols.map(c => <th key={c} style={{ textAlign: 'left', padding: '4px 6px', color: 'var(--text-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>{c}</th>)}
                      <th style={{ width: 26 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {sampleRows.map((r, ri) => (
                      <tr key={ri}>
                        {inputCols.map(c => (
                          <td key={c} style={{ padding: '2px 4px' }}>
                            <input style={{ ...input, padding: '5px 8px', width: 110 }} value={r[c] ?? ''} onChange={e => setCell(ri, c, e.target.value)} placeholder={c} />
                          </td>
                        ))}
                        <td style={{ padding: '2px 4px' }}>
                          <button type="button" onClick={() => removeSampleRow(ri)} title="Remove row"
                            style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--bg-border)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                            <X size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button type="button" onClick={addSampleRow}
                  style={{ marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600, border: `1px dashed ${accent}`, background: 'transparent', color: accent, cursor: 'pointer' }}>
                  <Plus size={12} /> Add row
                </button>
              </div>
            )}
            {previewTable}
          </div>
        )}
      </div>

      {/* MODAL — Visualize */}
      {showModal && (
        <div
          onClick={e => { if (e.target === e.currentTarget) setShowModal(false) }}
          style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
        >
          <div style={{ width: 900, maxWidth: '94vw', maxHeight: '90vh', background: 'var(--bg-card)', borderRadius: 16, border: '1px solid var(--bg-border)', boxShadow: '0 32px 80px rgba(0,0,0,0.65)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: '1px solid var(--bg-border)' }}>
              <h2 style={{ margin: 0, flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Script editor</h2>
              <button onClick={() => setShowModal(false)} style={{ width: 28, height: 28, borderRadius: 8, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={16} /></button>
            </div>
            {/* Toolbar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderBottom: '1px solid var(--bg-border)', flexWrap: 'wrap' }}>
              <button type="button" style={toolBtn} onClick={() => modalView && undo(modalView)} title="Undo (Ctrl+Z)"><Undo2 size={13} /> Undo</button>
              <button type="button" style={toolBtn} onClick={() => modalView && redo(modalView)} title="Redo (Ctrl+Y)"><Redo2 size={13} /> Redo</button>
              <span style={{ width: 1, height: 18, background: 'var(--bg-border)', margin: '0 2px' }} />
              <button type="button" style={toolBtn} onClick={() => doCut(modalView)} title="Cut"><Scissors size={13} /> Cut</button>
              <button type="button" style={toolBtn} onClick={() => doCopy(modalView)} title="Copy"><Copy size={13} /> Copy</button>
              <button type="button" style={toolBtn} onClick={() => doPaste(modalView)} title="Paste"><ClipboardPaste size={13} /> Paste</button>
              <span style={{ width: 1, height: 18, background: 'var(--bg-border)', margin: '0 2px' }} />
              <button type="button" style={{ ...toolBtn, color: accent }} onClick={runParse} title="Check syntax + sandbox"><CheckCircle2 size={13} /> Parse</button>
              <div style={{ flex: 1 }} />
              {parseMsg && (
                <span style={{ fontSize: 12, fontFamily: 'monospace', color: parseMsg.ok ? 'var(--success, #22c55e)' : 'var(--error)', maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={parseMsg.text}>
                  {parseMsg.ok ? '✓ ' : '✗ '}{parseMsg.text}
                </span>
              )}
            </div>
            {/* Editor */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
              {editor('58vh', v => setModalView(v))}
            </div>
            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '10px 16px', borderTop: '1px solid var(--bg-border)' }}>
              <button onClick={() => setShowModal(false)} style={{ padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: accent, border: 'none', color: '#fff' }}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
