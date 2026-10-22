/**
 * Ordre des cartes de workflows sur la page projet (glisser-déposer).
 * Purement visuel : rangé dans .hydra/project.json, sans effet sur thread.yaml.
 */

/** Déplace `dragId` à la place de `targetId` (les autres glissent d'un cran). */
export function moveTo(ids: string[], dragId: string, targetId: string): string[] {
  const from = ids.indexOf(dragId)
  const to = ids.indexOf(targetId)
  if (from < 0 || to < 0 || from === to) return ids
  const next = ids.filter(i => i !== dragId)
  next.splice(to, 0, dragId)
  return next
}

/** Échange les places de `a` et `b` (glisser une carte sur une autre). */
export function swap(ids: string[], a: string, b: string): string[] {
  const i = ids.indexOf(a)
  const j = ids.indexOf(b)
  if (i < 0 || j < 0 || i === j) return ids
  const next = [...ids]
  next[i] = b
  next[j] = a
  return next
}

/** Range `items` selon `ids` (les absents à la fin, ordre conservé). */
export function sortByIds<T extends { id: string }>(items: T[], ids: string[]): T[] {
  const rank = new Map(ids.map((id, i) => [id, i]))
  return [...items].sort((a, b) => (rank.get(a.id) ?? ids.length) - (rank.get(b.id) ?? ids.length))
}
