import { beforeEach, describe, expect, it } from 'vitest'
import { forgetProject, lastProject, projectSettingsPath, rememberProject } from './lastProject'

const store: Record<string, string> = {}
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k]
  ;(globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
  }
})

describe('dernier projet ouvert', () => {
  it('mémorise, relit, oublie', () => {
    expect(lastProject()).toBeNull()
    rememberProject({ id: 'p1', name: 'demo', path: 'C:\\data\\demo' })
    expect(lastProject()).toEqual({ id: 'p1', name: 'demo', path: 'C:\\data\\demo' })
    forgetProject('other'); expect(lastProject()?.id).toBe('p1')
    forgetProject('p1'); expect(lastProject()).toBeNull()
    expect(projectSettingsPath('p1')).toBe('/settings/project/p1')
  })
  it('stockage illisible : null, sans erreur', () => {
    store['hydra-last-project'] = '{oops'
    expect(lastProject()).toBeNull()
  })
})
