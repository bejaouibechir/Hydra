/**
 * ExpressionBuilder — « Expression Assistant », inspiré de l'Expression Builder
 * de SSIS : palette à gauche, description à droite, zone d'édition en bas.
 *
 * Deux usages :
 *  - mode 'expression' (expr de derive / filter) : opérateurs et fonctions
 *    pandas, plus les paramètres et variables d'environnement ;
 *  - mode 'value' (bouton {x} d'un champ : chemin, hôte, port, requête…) :
 *    paramètres, secrets et variables d'environnement seulement.
 *
 * Un élément de la palette s'insère au curseur par double-clic ou par
 * glisser-déposer dans la zone d'édition ; « Insert » renvoie le texte au champ.
 * L'en-tête montre l'environnement actif : les valeurs affichées des paramètres
 * sont celles de cet environnement (sinon leur défaut).
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api } from '@/lib/api'
import { EXPR_CATEGORIES, rewriteFriendlyConcat } from '@/lib/exprBuilder'
import { effectiveValue, getActiveEnv, setActiveEnv } from '@/lib/activeEnv'
import { hasRef } from '@/components/canvas/RefPicker'

export type AssistantMode = 'expression' | 'value'

interface Item {
  label: string
  text: string            // inséré dans la zone d'édition
  title: string
  desc: string
  details?: [string, string][]
}

interface Props {
  initialExpr: string
  accent?: string
  columns?: string[]                 // colonnes disponibles (optionnel)
  mode?: AssistantMode
  projectId?: string
  fieldLabel?: string                // champ cible (mode value)
  secretsOnly?: boolean              // mot de passe : secrets et environnement seulement
  onApply: (expr: string) => void
  onClose: () => void
}

const ENV_RE = /^[A-Za-z_][A-Za-z0-9_]*$/
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_.\-]*$/
const fmt = (v: unknown) => v === undefined ? '—' : typeof v === 'string' ? v : JSON.stringify(v)

export default function ExpressionBuilder({
  initialExpr, accent = 'var(--primary)', columns = [], mode = 'expression',
  projectId, fieldLabel, secretsOnly = false, onApply, onClose,
}: Props) {
  const [expr, setExpr] = useState(initialExpr ?? '')
  const firstCat = mode === 'expression' ? (EXPR_CATEGORIES[0]?.name ?? '') : (secretsOnly ? 'Secrets' : 'Parameters')
  const [open, setOpen] = useState<string>(firstCat)
  const [hover, setHover] = useState<Item | null>(null)
  const [envVar, setEnvVar] = useState('')
  const [otherParam, setOtherParam] = useState('')
  const taRef = useRef<HTMLTextAreaElement | null>(null)

  const paramsQ = useQuery({
    queryKey: ['parameters', projectId],
    queryFn: () => api.parameters.get(projectId as string),
    enabled: Boolean(projectId) && !secretsOnly,
  })
  const secretsQ = useQuery({
    queryKey: ['secrets', projectId],
    queryFn: () => api.secrets.list(projectId as string),
    enabled: Boolean(projectId) && mode === 'value',
  })
  const declarations = (paramsQ.data?.declarations ?? {}) as Record<string, Record<string, unknown>>
  const environments = (paramsQ.data?.environments ?? {}) as Record<string, Record<string, unknown>>
  const envNames = Object.keys(environments).sort()
  const [env, setEnv] = useState<string>(() => getActiveEnv(projectId) ?? '')
  useEffect(() => {
    if (!envNames.length) return
    if (!envNames.includes(env)) setEnv(envNames.includes('dev') ? 'dev' : envNames[0])
  }, [envNames.join('|')])                       // eslint-disable-line react-hooks/exhaustive-deps
  const chooseEnv = (e: string) => { setEnv(e); setActiveEnv(projectId, e) }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])

  // Dernière position du curseur dans la zone d'édition ; tant que
  // l'utilisateur n'y a pas cliqué, un double-clic ajoute à la fin.
  const caret = useRef<[number, number] | null>(null)
  const remember = () => { const ta = taRef.current; if (ta) caret.current = [ta.selectionStart, ta.selectionEnd] }
  const insert = (text: string) => {
    const ta = taRef.current
    if (!ta) { setExpr(e => (e ? e + ' ' : '') + text); return }
    const [s, e] = caret.current ?? [expr.length, expr.length]
    // Expression : un espace sépare l'élément inséré de ce qui le touche
    if (mode === 'expression') {
      const before = expr.slice(0, s), after = expr.slice(e)
      if (before && !/[\s(]$/.test(before)) text = ' ' + text
      if (after && !/^[\s),]/.test(after)) text = text + ' '
    }
    const next = expr.slice(0, s) + text + expr.slice(e)
    setExpr(next)
    const p = s + text.length
    caret.current = [p, p]
    requestAnimationFrame(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = p })
  }

  // ── Palette ────────────────────────────────────────────────────────────────
  const paramItems: Item[] = Object.keys(declarations).sort().map(name => {
    const d = declarations[name] ?? {}
    const eff = effectiveValue(name, declarations, environments, env)
    return {
      label: name, text: `{{ param:${name} }}`, title: name,
      desc: String(d.description ?? '') || 'Project parameter (parameters.yaml).',
      details: [
        ['Type', String(d.type ?? 'any')],
        ['Default', fmt(d.default)],
        [env ? `Value (${env})` : 'Value', eff.from === 'none' ? '— (no value: required at run time)' : `${fmt(eff.value)}${eff.from === 'default' ? '  (default)' : ''}`],
      ],
    }
  })
  const secretItems: Item[] = (secretsQ.data?.secrets ?? []).map(s => s.name).sort().map(name => ({
    label: name, text: '${SECRET:' + name + '}', title: name,
    desc: 'Secret from .hydra/secrets (or the configured provider). Its value is never shown and is masked in logs.',
    details: [['Overridden by', String((secretsQ.data?.secrets ?? []).find(s => s.name === name)?.overridden_by ?? '—')]],
  }))
  const columnItems: Item[] = columns.map(c => ({ label: c, text: c, title: c, desc: 'Column of the current flow.' }))

  type Cat = { name: string; items: Item[]; empty?: string; extra?: 'env' | 'param' }
  const cats: Cat[] = []
  if (mode === 'expression') {
    if (columnItems.length) cats.push({ name: 'Columns', items: columnItems })
    for (const c of EXPR_CATEGORIES)
      cats.push({ name: c.name, items: c.fns.map(f => ({ label: f.label, text: f.template, title: f.label, desc: f.desc })) })
  }
  if (!secretsOnly) cats.push({ name: 'Parameters', items: paramItems, extra: 'param',
    empty: !projectId ? 'Open a project to list its parameters.' : paramsQ.isLoading ? 'Loading…' : 'No parameter declared in parameters.yaml (Parameters tab).' })
  if (mode === 'value') cats.push({ name: 'Secrets', items: secretItems,
    empty: !projectId ? 'Open a project to list its secrets.' : secretsQ.isLoading ? 'Loading…' : 'No secret yet: add one in the Secrets tab.' })
  cats.push({ name: 'Environment variables', items: [], extra: 'env' })

  const envOk = ENV_RE.test(envVar.trim())
  const otherOk = NAME_RE.test(otherParam.trim())

  const translated = mode === 'expression' && !hasRef(expr) ? rewriteFriendlyConcat(expr) : expr
  const changed = translated !== expr

  const labelStyle = { fontSize: 11, fontWeight: 600 as const, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.05em' }
  const small: React.CSSProperties = { boxSizing: 'border-box', width: '100%', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, outline: 'none', fontFamily: 'monospace' }
  const chip = (enabled: boolean): React.CSSProperties => ({ display: 'inline-block', padding: '3px 8px', borderRadius: 6, fontSize: 12, fontFamily: 'monospace', border: `1px solid ${enabled ? accent : 'var(--bg-border)'}`, color: enabled ? accent : 'var(--text-muted)', background: 'transparent', cursor: enabled ? 'grab' : 'not-allowed', marginRight: 6, marginTop: 6 })

  const dragProps = (text: string) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => { e.dataTransfer.setData('text/plain', text); e.dataTransfer.effectAllowed = 'copy' },
  })

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
    >
      <div style={{ width: 760, maxHeight: '86vh', background: 'var(--bg-card)', borderRadius: 16, border: '1px solid var(--bg-border)', boxShadow: '0 32px 80px rgba(0,0,0,0.65)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* En-tête : titre + environnement actif */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: '1px solid var(--bg-border)' }}>
          <span style={{ fontStyle: 'italic', fontWeight: 800, fontSize: 16, color: accent }}>{mode === 'expression' ? 'fx' : '{x}'}</span>
          <h2 style={{ margin: 0, flex: 1, fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
            Expression Assistant{fieldLabel ? <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> — {fieldLabel}</span> : null}
          </h2>
          {!secretsOnly && (
            <label title="Parameter values shown for this environment (environments/<env>.yaml)"
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
              Environment:
              {envNames.length ? (
                <select value={env} onChange={e => chooseEnv(e.target.value)}
                  style={{ background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 6, padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12, cursor: 'pointer' }}>
                  {envNames.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              ) : <span style={{ color: 'var(--text-muted)' }}>defaults only</span>}
            </label>
          )}
          <button onClick={onClose} style={{ width: 28, height: 28, borderRadius: 8, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={15} /></button>
        </div>

        {/* Palette (gauche) + description (droite) */}
        <div style={{ display: 'flex', flex: 1, minHeight: 260, overflow: 'hidden' }}>
          <div style={{ width: 280, overflowY: 'auto', borderRight: '1px solid var(--bg-border)', padding: 10 }}>
            {cats.map(cat => (
              <div key={cat.name} style={{ marginBottom: 4 }}>
                <button onClick={() => setOpen(o => o === cat.name ? '' : cat.name)}
                  style={{ width: '100%', textAlign: 'left', padding: '7px 8px', borderRadius: 6, border: 'none', background: open === cat.name ? 'var(--bg-hover)' : 'transparent', color: 'var(--text-primary)', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                  {open === cat.name ? '▾' : '▸'} {cat.name}
                  {cat.items.length > 0 && <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> ({cat.items.length})</span>}
                </button>
                {open === cat.name && (
                  <div style={{ padding: '2px 0 6px' }}>
                    {cat.items.map(it => (
                      <button key={it.label} type="button" {...dragProps(it.text)}
                        onClick={() => setHover(it)} onMouseEnter={() => setHover(it)} onDoubleClick={() => insert(it.text)}
                        title="Double-click or drag into the expression"
                        style={{ display: 'block', width: '100%', textAlign: 'left', padding: '5px 8px 5px 22px', borderRadius: 6, border: 'none', background: hover?.label === it.label ? 'var(--bg-hover)' : 'transparent', color: 'var(--text-secondary)', fontSize: 12, cursor: 'grab', fontFamily: cat.name === 'Parameters' || cat.name === 'Secrets' ? 'monospace' : undefined }}>
                        {it.label}
                      </button>
                    ))}
                    {cat.items.length === 0 && cat.empty && (
                      <div style={{ padding: '4px 8px 4px 22px', fontSize: 11, color: 'var(--text-muted)' }}>{cat.empty}</div>
                    )}
                    {cat.extra === 'param' && projectId && (
                      <div style={{ padding: '6px 8px 2px 22px' }}>
                        <input style={small} value={otherParam} onChange={e => setOtherParam(e.target.value)} placeholder="other name (set_param…)" />
                        {otherOk && <span style={chip(true)} {...dragProps(`{{ param:${otherParam.trim()} }}`)}
                          onDoubleClick={() => insert(`{{ param:${otherParam.trim()} }}`)}>{`{{ param:${otherParam.trim()} }}`}</span>}
                      </div>
                    )}
                    {cat.extra === 'env' && (
                      <div style={{ padding: '4px 8px 2px 22px' }}>
                        <input style={small} value={envVar} onChange={e => setEnvVar(e.target.value)} placeholder="DATA_DIR"
                          onFocus={() => setHover({ label: 'env', text: '', title: 'Environment variable',
                            desc: 'Type the variable name, then double-click or drag one of the two forms. Required: the run stops if the variable is missing. Optional: empty when missing.' })} />
                        {envOk && (
                          <div>
                            <span style={chip(true)} {...dragProps('${ENV:' + envVar.trim() + '}')} title="Required: the run stops if it is missing"
                              onDoubleClick={() => insert('${ENV:' + envVar.trim() + '}')}>{'${ENV:' + envVar.trim() + '}'}</span>
                            {!secretsOnly && (
                              <span style={chip(true)} {...dragProps(`{{ env:${envVar.trim()} }}`)} title="Optional: empty when missing"
                                onDoubleClick={() => insert(`{{ env:${envVar.trim()} }}`)}>{`{{ env:${envVar.trim()} }}`}</span>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
            <div style={{ ...labelStyle, marginBottom: 8 }}>Description</div>
            {hover ? (
              <div>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: 13, marginBottom: 6 }}>{hover.title}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 10 }}>{hover.desc}</div>
                {hover.details && (
                  <table style={{ fontSize: 12, marginBottom: 10, borderCollapse: 'collapse' }}>
                    <tbody>
                      {hover.details.map(([k, v]) => (
                        <tr key={k}><td style={{ color: 'var(--text-muted)', padding: '2px 12px 2px 0' }}>{k}</td>
                          <td style={{ color: 'var(--text-primary)', fontFamily: 'monospace' }}>{v}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {hover.text && (
                  <code {...dragProps(hover.text)} onDoubleClick={() => insert(hover.text)}
                    style={{ display: 'block', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 10px', fontSize: 12, color: accent, fontFamily: 'monospace', cursor: 'grab' }}>
                    {hover.text}
                  </code>
                )}
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>
                Select an item to see its description. Double-click it, or drag it into the expression below.
                {mode === 'expression' && <> Replace <code>col</code> / <code>col1</code> with your column names.</>}
              </div>
            )}
          </div>
        </div>

        {/* Zone d'édition */}
        <div style={{ padding: 16, borderTop: '1px solid var(--bg-border)' }}>
          <div style={{ ...labelStyle, marginBottom: 6 }}>{mode === 'expression' ? 'Expression' : 'Value'}</div>
          <textarea
            ref={taRef}
            value={expr}
            onChange={e => { setExpr(e.target.value); remember() }}
            onSelect={remember} onKeyUp={remember} onClick={remember}
            onDrop={() => requestAnimationFrame(remember)}
            rows={3}
            placeholder={mode === 'expression'
              ? "e.g. first + ' ' + last   ·   price * qty   ·   amount * {{ param:rate }}"
              : 'e.g. {{ param:data_dir }}/orders.csv   ·   ${SECRET:db.password}'}
            style={{ display: 'block', width: '100%', boxSizing: 'border-box', resize: 'vertical', background: 'var(--bg-input)', border: '1px solid var(--bg-border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'monospace', outline: 'none' }}
          />
          {changed && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              → engine: <code style={{ color: accent, fontFamily: 'monospace' }}>{translated}</code>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '12px 18px', borderTop: '1px solid var(--bg-border)' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', background: 'transparent', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }}>Cancel</button>
          <button onClick={() => onApply(translated)} style={{ padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: accent, border: 'none', color: '#fff' }}>Insert</button>
        </div>
      </div>
    </div>
  )
}
