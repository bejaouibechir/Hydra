/**
 * RefPicker — bouton « {x} » à côté d'un champ : ouvre l'Expression Assistant
 * (mode valeur) pour insérer une référence au lieu d'une valeur en dur. Paramètre {{ param:NAME }}, secret ${SECRET:NAME},
 * variable d'environnement ${ENV:NAME} (exigée) ou {{ env:NAME }} (facultative).
 * Le moteur résout ces références dans tous les YAML d'un job et dans les
 * params des actions de workflow.
 */

// Champs où une référence a du sens : valeurs qui changent d'un environnement à
// l'autre (chemins, hôtes, bases, tables, URL), valeurs sensibles, seuils et
// délais, expressions. Pas les noms de colonnes, mappings ni listes à choix.
const REF_KEYS = new Set([
  'path', 'host', 'port', 'instance', 'database', 'schema', 'user', 'uri', 'collection',
  'table', 'query', 'url',
  'expr', 'value', 'max_rows',
  'message', 'body', 'headers', 'to', 'subject', 'from_addr', 'smtp_host', 'smtp_port',
  'username', 'command', 'working_dir', 'timeout', 'key_path', 'file_path', 'script', 'seconds',
])
// value / filter / expr : selon le nœud
const NOT_FOR: Record<string, string[]> = {
  value: ['action_condition'],
}

export function acceptsRefs(nodeType: string, key: string, type?: string): boolean {
  if (type === 'select') return false
  if (!REF_KEYS.has(key)) return false
  return !(NOT_FOR[key] ?? []).includes(nodeType)
}

/** La valeur est-elle (ou contient-elle) une référence ? */
export function hasRef(v: unknown): boolean {
  return typeof v === 'string' && /\{\{\s*(param|env)\s*:|\$\{(ENV|SECRET):/.test(v)
}

/** Insère `text` dans `value` à la sélection [start, end) ; remplace tout si `replace`. */
export function insertAt(value: string, text: string, start?: number | null, end?: number | null, replace = false): string {
  if (replace || !value) return text
  const s = start ?? value.length
  const e = end ?? s
  return value.slice(0, s) + text + value.slice(e)
}

interface ButtonProps {
  accent?: string
  label?: string                      // '{x}' (valeur) ou 'fx' (expression)
  title?: string
  onClick: () => void
}

/** Bouton d'ouverture de l'Expression Assistant à côté d'un champ. */
export default function RefButton({ accent = 'var(--primary)', label = '{x}', title, onClick }: ButtonProps) {
  return (
    <button type="button" onClick={onClick}
      title={title ?? 'Expression Assistant: insert a parameter, a secret or an environment variable'}
      style={{ flexShrink: 0, minHeight: 36, padding: '0 10px', borderRadius: 8, fontSize: 13, fontWeight: 800, fontStyle: 'italic',
               fontFamily: label === 'fx' ? undefined : 'monospace', border: '1px solid var(--bg-border)', background: 'var(--bg-hover)',
               color: accent, cursor: 'pointer' }}>
      {label}
    </button>
  )
}
