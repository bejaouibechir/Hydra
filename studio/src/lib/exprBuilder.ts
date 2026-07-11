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
    name: 'Opérateurs',
    fns: [
      { label: '+  Addition',        template: 'col1 + col2',  desc: 'Somme de deux colonnes numériques.' },
      { label: '−  Soustraction',    template: 'col1 - col2',  desc: 'Différence de deux colonnes.' },
      { label: '×  Multiplication',  template: 'col1 * col2',  desc: 'Produit de deux colonnes.' },
      { label: '÷  Division',        template: 'col1 / col2',  desc: 'Quotient de deux colonnes.' },
      { label: '%  Modulo',          template: 'col1 % col2',  desc: 'Reste de la division entière.' },
    ],
  },
  {
    name: 'Maths',
    fns: [
      { label: 'Arrondi',        template: 'col.round(2)', desc: 'Arrondit à N décimales.' },
      { label: 'Valeur absolue', template: 'abs(col)',     desc: 'Valeur absolue.' },
      { label: 'Racine carrée',  template: 'sqrt(col)',    desc: 'Racine carrée.' },
      { label: 'Logarithme',     template: 'log(col)',     desc: 'Logarithme naturel.' },
      { label: 'Puissance',      template: 'col ** 2',     desc: 'Élévation à la puissance.' },
    ],
  },
  {
    name: 'Chaînes',
    fns: [
      { label: 'Majuscules',       template: "col.str.upper()",                    desc: 'Convertit en majuscules.' },
      { label: 'Minuscules',       template: "col.str.lower()",                    desc: 'Convertit en minuscules.' },
      { label: 'Longueur',         template: "col.str.len()",                      desc: 'Nombre de caractères.' },
      { label: 'Concaténer',       template: "col1.str.cat(col2, sep=' ')",        desc: 'Assemble deux colonnes texte avec un séparateur.' },
      { label: 'Remplacer',        template: "col.str.replace('ancien', 'nouveau')", desc: 'Remplace un motif par un autre.' },
      { label: 'Contient',         template: "col.str.contains('texte')",          desc: 'Vrai si la colonne contient le texte.' },
      { label: 'Sous-chaîne',      template: "col.str.slice(0, 3)",                desc: 'Extrait les caractères de début à fin (0-basé).' },
      { label: 'Supprimer espaces', template: "col.str.strip()",                   desc: 'Enlève les espaces en début/fin.' },
    ],
  },
  {
    name: 'Date / Heure',
    fns: [
      { label: 'Année',            template: 'col.dt.year',                desc: "Année d'une colonne datetime." },
      { label: 'Mois',             template: 'col.dt.month',               desc: 'Mois (1-12).' },
      { label: 'Jour',             template: 'col.dt.day',                 desc: 'Jour du mois.' },
      { label: 'Format',           template: "col.dt.strftime('%Y-%m-%d')", desc: 'Formate la date en texte.' },
      { label: 'Différence (jours)', template: '(col2 - col1).dt.days',    desc: 'Nombre de jours entre deux dates.' },
    ],
  },
  {
    name: 'Conversion',
    fns: [
      { label: 'Vers entier',  template: "col.astype('int')",   desc: 'Convertit en entier.' },
      { label: 'Vers décimal', template: "col.astype('float')", desc: 'Convertit en décimal.' },
      { label: 'Vers texte',   template: "col.astype('str')",   desc: 'Convertit en texte.' },
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
