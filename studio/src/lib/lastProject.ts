/**
 * lib/lastProject.ts — Dernier projet ouvert dans Studio (ce navigateur).
 *
 * Sert à l'onglet Settings › Project settings quand on y arrive par le menu,
 * sans passer par la page d'un projet. Stocké dans localStorage : un accès
 * refusé ou vide n'empêche rien (on demande alors de choisir un projet).
 */
export interface LastProject { id: string; name: string; path: string }

const KEY = 'hydra-last-project'

export function rememberProject(p: LastProject): void {
  try { localStorage.setItem(KEY, JSON.stringify({ id: p.id, name: p.name, path: p.path })) } catch { /* ignoré */ }
}

export function lastProject(): LastProject | null {
  try {
    const raw = localStorage.getItem(KEY)
    const p = raw ? JSON.parse(raw) : null
    return p && typeof p.id === 'string' && p.id ? p as LastProject : null
  } catch { return null }
}

export function forgetProject(id: string): void {
  try { if (lastProject()?.id === id) localStorage.removeItem(KEY) } catch { /* ignoré */ }
}

/** Lien vers l'onglet Project settings d'un projet. */
export const projectSettingsPath = (id: string) => `/settings/project/${id}`
