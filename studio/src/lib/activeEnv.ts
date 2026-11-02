/**
 * activeEnv — environnement actif du projet dans Studio (dev, prod…), partagé
 * entre la page du projet, l'en-tête de l'éditeur, l'onglet Parameters et
 * l'Expression Assistant. Conservé par projet dans le navigateur ; sans stockage
 * disponible, retombe sur la valeur par défaut (aucun environnement).
 *
 * Les runs lancés depuis Studio reçoivent cet environnement : le serveur charge
 * ~/.hydra/env puis ~/.hydra/env.<env>, environments/<env>.yaml et
 * .hydra/secrets.<env>, comme `hdrctl run --env <env>`.
 */
import { useEffect, useState } from 'react'

const KEY = (projectId?: string) => `hydra.activeEnv.${projectId ?? '_'}`
const EVENT = 'hydra:active-env'

export function getActiveEnv(projectId?: string): string | null {
  try { return localStorage.getItem(KEY(projectId)) } catch { return null }
}

/** env vide : aucun environnement (comportement sans --env). */
export function setActiveEnv(projectId: string | undefined, env: string): void {
  try {
    if (env) localStorage.setItem(KEY(projectId), env)
    else localStorage.removeItem(KEY(projectId))
  } catch { /* stockage indisponible : sans effet */ }
  try { window.dispatchEvent(new CustomEvent(EVENT, { detail: { projectId, env } })) } catch { /* hors navigateur */ }
}

/** Environnement à passer à un run (undefined : aucun). */
export function envForRun(projectId?: string): string | undefined {
  return getActiveEnv(projectId) || undefined
}

/** Environnement actif, tenu à jour quand un autre sélecteur le change. */
export function useActiveEnv(projectId?: string): [string, (env: string) => void] {
  const [env, setEnv] = useState<string>(() => getActiveEnv(projectId) ?? '')
  useEffect(() => {
    setEnv(getActiveEnv(projectId) ?? '')
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail as { projectId?: string; env: string } | undefined
      if (!d || d.projectId === projectId) setEnv(d?.env ?? '')
    }
    window.addEventListener(EVENT, on)
    return () => window.removeEventListener(EVENT, on)
  }, [projectId])
  return [env, (v: string) => { setEnv(v); setActiveEnv(projectId, v) }]
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
