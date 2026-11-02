import { describe, expect, it } from 'vitest'
import { effectiveValue, envForRun, getActiveEnv, setActiveEnv } from './activeEnv'
import { typedValue } from '@/components/canvas/ParametersPanel'

// Environnement node : un localStorage et un window minimaux
const store = new Map<string, string>()
;(globalThis as { localStorage?: unknown }).localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => { store.set(k, v) },
  removeItem: (k: string) => { store.delete(k) },
}
if (!(globalThis as { window?: unknown }).window) {
  const target = new EventTarget()
  ;(globalThis as { window?: unknown }).window = {
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    dispatchEvent: target.dispatchEvent.bind(target),
  }
}

describe('activeEnv', () => {
  it('stores the environment per project; empty means no environment', () => {
    setActiveEnv('p1', 'prod')
    setActiveEnv('p2', 'dev')
    expect(getActiveEnv('p1')).toBe('prod')
    expect(envForRun('p2')).toBe('dev')
    setActiveEnv('p1', '')
    expect(getActiveEnv('p1')).toBeNull()
    expect(envForRun('p1')).toBeUndefined()
  })

  it('notifies the other selectors', () => {
    let seen = ''
    const on = (e: Event) => { seen = (e as CustomEvent).detail.env }
    window.addEventListener('hydra:active-env', on)
    setActiveEnv('p3', 'qa')
    window.removeEventListener('hydra:active-env', on)
    expect(seen).toBe('qa')
  })

  it('effective value: environment, then default', () => {
    const decl = { batch: { type: 'int', default: 500 } }
    expect(effectiveValue('batch', decl, { prod: { batch: 5000 } }, 'prod')).toEqual({ value: 5000, from: 'environment' })
    expect(effectiveValue('batch', decl, { prod: { batch: 5000 } }, '')).toEqual({ value: 500, from: 'default' })
  })
})

describe('typedValue', () => {
  it('converts the typed text to the declared type', () => {
    expect(typedValue('42', 'int')).toBe(42)
    expect(typedValue('4.5', 'float')).toBe(4.5)
    expect(typedValue('TRUE', 'bool')).toBe(true)
    expect(typedValue('{"a":1}', 'json')).toEqual({ a: 1 })
    expect(typedValue('abc', 'int')).toBe('abc')
    expect(typedValue(' x ', 'string')).toBe(' x ')
  })
})
