/**
 * ExpressionBuilder — assistant de saisie d'expression pour le nœud derive.
 * Inspiré de l'Expression Builder de SSIS : palette de fonctions groupées +
 * zone d'édition + aperçu de la traduction moteur (concat conviviale).
 */
import { useState, useRef } from 'react'
import { X } from 'lucide-react'
import { EXPR_CATEGORIES, rewriteFriendlyConcat, type ExprFn } from '@/lib/exprBuilder'

interface Props {
  initialExpr: string
  accent?: string
  columns?: string[]                 // colonnes disponibles (optionnel)
  onApply: (expr: string) => void
  onClose: () => void
}

export default function ExpressionBuilder({ initialExpr, accent = 'var(--primary)', columns = [], onApply, onClose }: Props) {
  const [expr, setExpr] = useState(initialExpr ?? '')
  const [open, setOpen] = useState<string>(EXPR_CATEGORIES[0]?.name ?? '')
  const [hover, setHover] = useState<ExprFn | null>(null)
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  const insert = (text: string) => {
    const ta = taRef.current
    if (!ta) { setExpr(e => (e ? e + ' ' : '') + text); return }
    const s = ta.selectionStart ?? expr.length
    const e = ta.selectionEnd ?? expr.length
    const next = expr.slice(0, s) + text + expr.slice(e)
    setExpr(next)
    requestAnimationFrame(() => { ta.focus(); const p = s + text.length; ta.selectionStart = ta.selectionEnd = p })
  }

  const translated = rewriteFriendlyConcat(expr)
  const changed = translated !== expr

  const labelStyle = { fontSize: 11, fontWeight: 600 as const, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.05em' }

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
    >
      <div style={{ width: 720, maxHeight: '86vh', background: 'var(--bg-card)', borderRadius: 16, border: '1px solid var(--bg-border)', boxShadow: '0 32px 80px rgba(0,0,0,0.65)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: '1px solid var(--bg-border)' }}>
          <span style={{ fontStyle: 'italic', fontWeight: 800, fontSize: 16, color: accent }}>fx</span>
          <h2 style={{ margin: 0, flex: 1, fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>Expression Assistant</h2>
          <button onClick={onClose} style={{ width: 28, height: 28, borderRadius: 8, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={15} /></button>
        </div>

        {/* Body : palette (gauche) + description (droite) */}
        <div style={{ display: 'flex', gap: 0, flex: 1, minHeight: 240, overflow: 'hidden' }}>

          {/* Colonnes + fonctions */}
          <div style={{ width: 280, overflowY: 'auto', borderRight: '1px solid var(--bg-border)', padding: 10 }}>
            {columns.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ ...labelStyle, marginBottom: 6 }}>Columns</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {columns.map(c => (
                    <button key={c} onClick={() => insert(c)} style={{ padding: '3px 8px', borderRadius: 6, fontSize: 12, border: '1px solid var(--bg-border)', background: 'var(--bg-hover)', color: 'var(--text-secondary)', cursor: 'pointer' }}>{c}</button>
                  ))}
                </div>
              </div>
            )}
            {EXPR_CATEGORIES.map(cat => (
              <div key={cat.name} style={{ marginBottom: 4 }}>
                <button
                  onClick={() => setOpen(o => o === cat.name ? '' : cat.name)}
                  style={{ width: '100%', textAlign: 'left', padding: '7px 8px', borderRadius: 6, border: 'none', background: open === cat.name ? 'var(--bg-hover)' : 'transparent', color: 'var(--text-primary)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
                >
                  {open === cat.name ? '▾' : '▸'} {cat.name}
                </button>
                {open === cat.name && (
                  <div style={{ padding: '2px 0 6px' }}>
                    {cat.fns.map(fn => (
                      <button
                        key={fn.label}
                        onClick={() => insert(fn.template)}
                        onMouseEnter={() => setHover(fn)}
                        style={{ display: 'block', width: '100%', textAlign: 'left', padding: '5px 8px 5px 22px', borderRadius: 6, border: 'none', background: 'transparent', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}
                      >
                        {fn.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Description */}
          <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
            <div style={{ ...labelStyle, marginBottom: 8 }}>Description</div>
            {hover ? (
              <div>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: 13, marginBottom: 6 }}>{hover.label}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 10 }}>{hover.desc}</div>
                <code style={{ display: 'block', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: accent, fontFamily: 'monospace' }}>{hover.template}</code>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                Hover a function to see its description. Click to insert.
                Replace <code>col</code> / <code>col1</code> with your column names.
              </div>
            )}
          </div>
        </div>

        {/* Expression + aperçu moteur */}
        <div style={{ padding: 16, borderTop: '1px solid var(--bg-border)' }}>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Expression</div>
          <textarea
            ref={taRef}
            value={expr}
            onChange={e => setExpr(e.target.value)}
            rows={3}
            placeholder="e.g. first + ' ' + last   ·   price * qty   ·   date.dt.year"
            style={{ display: 'block', width: '100%', boxSizing: 'border-box', resize: 'vertical', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'monospace', outline: 'none' }}
          />
          {changed && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              → engine: <code style={{ color: accent, fontFamily: 'monospace' }}>{translated}</code>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '12px 18px', borderTop: '1px solid var(--bg-border)' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', background: 'transparent', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }}>Cancel</button>
          <button onClick={() => onApply(translated)} style={{ padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: accent, border: 'none', color: '#fff' }}>Insert</button>
        </div>
      </div>
    </div>
  )
}
