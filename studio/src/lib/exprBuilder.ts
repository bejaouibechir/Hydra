/**
 * exprBuilder — catalogue de fonctions + traduction conviviale pour le nœud derive.
 *
 * Le moteur Hydra évalue l'expression via pandas `DataFrame.eval(engine="python")`.
 * Ce module fournit :
 *   - EXPR_CATEGORIES : fonctions groupées (style SSIS) qui insèrent du pandas correct.
 *   - rewriteFriendlyConcat : traduit `a + ' ' + b` → `a.str.cat(b, sep=' ')`
 *     UNIQUEMENT si un littéral texte est présent (sinon `+` reste une addition).
 */

export interface ExprFn {
  label: string
  template: string   // pandas inséré (⟨col⟩ = placeholder à remplacer)
  desc: string
}

export interface ExprCategory {
  name: string
  fns: ExprFn[]
}

export const EXPR_CATEGORIES: ExprCategory[] = [
  {
    name: 'Operators',
    fns: [
      { label: '+  Addition',        template: 'col1 + col2',  desc: 'Sum of two numeric columns.' },
      { label: '−  Subtraction',    template: 'col1 - col2',  desc: 'Difference of two columns.' },
      { label: '×  Multiplication',  template: 'col1 * col2',  desc: 'Product of two columns.' },
      { label: '÷  Division',        template: 'col1 / col2',  desc: 'Quotient of two columns.' },
      { label: '%  Modulo',          template: 'col1 % col2',  desc: 'Remainder of integer division.' },
    ],
  },
  {
    name: 'Math',
    fns: [
      { label: 'Round',        template: 'col.round(2)', desc: 'Rounds to N decimals.' },
      { label: 'Absolute value', template: 'abs(col)',     desc: 'Absolute value.' },
      { label: 'Square root',  template: 'sqrt(col)',    desc: 'Square root.' },
      { label: 'Logarithm',     template: 'log(col)',     desc: 'Natural logarithm.' },
      { label: 'Power',      template: 'col ** 2',     desc: 'Exponentiation.' },
    ],
  },
  {
    name: 'Strings',
    fns: [
      { label: 'Uppercase',       template: "col.str.upper()",                    desc: 'Converts to uppercase.' },
      { label: 'Lowercase',       template: "col.str.lower()",                    desc: 'Converts to lowercase.' },
      { label: 'Length',         template: "col.str.len()",                      desc: 'Number of characters.' },
      { label: 'Concatenate',       template: "col1.str.cat(col2, sep=' ')",        desc: 'Joins two text columns with a separator.' },
      { label: 'Replace',        template: "col.str.replace('ancien', 'nouveau')", desc: 'Replaces one pattern with another.' },
      { label: 'Contains',         template: "col.str.contains('texte')",          desc: 'True if the column contains the text.' },
      { label: 'Substring',      template: "col.str.slice(0, 3)",                desc: 'Extracts characters from start to end (0-based).' },
      { label: 'Trim spaces', template: "col.str.strip()",                   desc: 'Removes leading/trailing spaces.' },
    ],
  },
  {
    name: 'Date / Time',
    fns: [
      { label: 'Year',            template: 'col.dt.year',                desc: "Année d'une colonne datetime." },
      { label: 'Month',             template: 'col.dt.month',               desc: 'Month (1-12).' },
      { label: 'Day',             template: 'col.dt.day',                 desc: 'Day of month.' },
      { label: 'Format',           template: "col.dt.strftime('%Y-%m-%d')", desc: 'Formats the date as text.' },
      { label: 'Difference (days)', template: '(col2 - col1).dt.days',    desc: 'Number of days between two dates.' },
    ],
  },
  {
    name: 'Conversion',
    fns: [
      { label: 'To integer',  template: "col.astype('int')",   desc: 'Converts to integer.' },
      { label: 'To decimal', template: "col.astype('float')", desc: 'Converts to decimal.' },
      { label: 'To text',   template: "col.astype('str')",   desc: 'Converts to text.' },
    ],
  },
]

// ── Traduction conviviale : concaténation avec '+' (si littéral présent) ──────

function splitTopLevelPlus(s: string): string[] {
  const parts: string[] = []
  let depth = 0
  let q: string | null = null
  let cur = ''
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (q) { cur += c; if (c === q) q = null; continue }
    if (c === "'" || c === '"') { q = c; cur += c; continue }
    if (c === '(' || c === '[' || c === '{') { depth++; cur += c; continue }
    if (c === ')' || c === ']' || c === '}') { depth--; cur += c; continue }
    if (c === '+' && depth === 0) { parts.push(cur); cur = ''; continue }
    cur += c
  }
  parts.push(cur)
  return parts.map(p => p.trim())
}

const isLit = (t: string): boolean =>
  (t.startsWith("'") && t.endsWith("'")) || (t.startsWith('"') && t.endsWith('"'))
const litVal = (t: string): string => t.slice(1, -1)

/**
 * Traduit une concaténation conviviale en pandas `.str.cat`, mais SEULEMENT
 * dans les cas non ambigus (au moins un littéral texte, motif col+sep+col régulier).
 * Sinon retourne l'expression inchangée (une addition numérique n'est jamais touchée).
 */
export function rewriteFriendlyConcat(expr: string): string {
  const e = (expr ?? '').trim()
  if (!e.includes('+')) return expr
  const parts = splitTopLevelPlus(e)
  if (parts.length < 2) return expr
  if (!parts.some(isLit)) return expr                         // aucun littéral → ambigu
  if (isLit(parts[0]) || isLit(parts[parts.length - 1])) return expr  // littéral en tête/queue
  const cols: string[] = []
  const seps: string[] = []
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { if (isLit(parts[i])) return expr; cols.push(parts[i]) }
    else { if (!isLit(parts[i])) return expr; seps.push(litVal(parts[i])) }
  }
  if (cols.length < 2) return expr
  if (!seps.every(s => s === seps[0])) return expr             // séparateurs différents
  const sep = seps[0].replace(/'/g, "\\'")
  const head = cols[0]
  const rest = cols.slice(1)
  return rest.length === 1
    ? `${head}.str.cat(${rest[0]}, sep='${sep}')`
    : `${head}.str.cat([${rest.join(', ')}], sep='${sep}')`
}
