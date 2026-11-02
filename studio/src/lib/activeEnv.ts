/**
 * activeEnv — environnement actif du projet dans Studio (dev, prod…), partagé
 * entre l'onglet Parameters et l'Expression Assistant. Conservé par projet dans
 * le navigateur ; sans stockage disponible, retombe sur la valeur par défaut.
 */
const KEY = (projectId?: string) => `hydra.activeEnv.${projectId ?? '_'}`

export function getActiveEnv(projectId?: string): string | null {
  try { return localStorage.getItem(KEY(projectId)) } catch { return null }
}

export function setActiveEnv(projectId: string | undefined, env: string): void {
  try { localStorage.setItem(KEY(projectId), env) } catch { /* stockage indisponible : sans effet */ }
}

/** Valeur effective d'un paramètre : celle de l'environnement, sinon le défaut. */
export function effectiveValue(
  name: string,
  declarations: Record<string, Record<string, unknown>>,
  environments: Record<string, Record<string, unknown>>,
  env: string,
): { value: unknown; from: 'environment' | 'default' | 'none' } {
  const envVals = (environments?.[env] ?? {}) as Record<string, unknown>
  if (envVals[name] !== undefined && envVals[name] !== null && envVals[name] !== '') return { value: envVals[name], from: 'environment' }
  const d = (declarations?.[name] ?? {}) as Record<string, unknown>
  if (d.default !== undefined && d.default !== null) return { value: d.default, from: 'default' }
  return { value: undefined, from: 'none' }
}
