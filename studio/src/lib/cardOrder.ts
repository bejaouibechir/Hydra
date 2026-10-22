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

/** Range `items` selon `ids` (les absents à la fin, ordre conservé). */
export function sortByIds<T extends { id: string }>(items: T[], ids: string[]): T[] {
  const rank = new Map(ids.map((id, i) => [id, i]))
  return [...items].sort((a, b) => (rank.get(a.id) ?? ids.length) - (rank.get(b.id) ?? ids.length))
}
