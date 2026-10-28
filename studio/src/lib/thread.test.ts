import { describe, it, expect } from 'vitest'
import { appendWorkflow, forSave, isValidDelay, isValidTimeout, moveWorkflow, namesIn, removeWorkflow, type ThreadStage } from './thread'

const S = (): ThreadStage[] => [
  { mode: 'sequential', workflows: [{ name: 'a', active: true }, { name: 'b', active: true }] },
  { mode: 'parallel', delay_after: '', workflows: [{ name: 'c', active: false }] },
]

describe('thread', () => {
  it('déplace dans une étape puis entre étapes', () => {
    expect(namesIn(moveWorkflow(S(), 0, 1, -1))).toEqual(['b', 'a', 'c'])
    const down = moveWorkflow(S(), 0, 1, 1)                      // b -> début de l'étape 2
    expect(down.map(s => s.workflows.map(w => w.name))).toEqual([['a'], ['b', 'c']])
    const up = moveWorkflow(S(), 1, 0, -1)                       // c -> fin de l'étape 1
    expect(up.map(s => s.workflows.map(w => w.name))).toEqual([['a', 'b', 'c'], []])
    expect(namesIn(moveWorkflow(S(), 0, 0, -1))).toEqual(['a', 'b', 'c'])   // déjà en tête
    expect(namesIn(moveWorkflow(S(), 1, 0, 1))).toEqual(['a', 'b', 'c'])    // déjà en queue
  })

  it('ajoute en fin : dernière étape séquentielle, sinon nouvelle étape', () => {
    expect(appendWorkflow(S(), 'd').map(s => s.workflows.map(w => w.name))).toEqual([['a', 'b'], ['c'], ['d']])
    expect(appendWorkflow([S()[0]], 'd')[0].workflows.map(w => w.name)).toEqual(['a', 'b', 'd'])
    expect(appendWorkflow([], 'd')).toEqual([{ mode: 'sequential', workflows: [{ name: 'd', active: true }] }])
  })

  it('prépare l\'envoi : étapes vides et délais vides retirés', () => {
    const s = removeWorkflow(S(), 1, 0)
    expect(forSave(s)).toEqual([{ mode: 'sequential', workflows: [{ name: 'a', active: true }, { name: 'b', active: true }] }])
    expect(forSave([{ mode: 'sequential', delay_after: ' 30s ', workflows: [{ name: 'a', active: true }] }])[0].delay_after).toBe('30s')
  })

  it('valide les délais comme le moteur', () => {
    for (const ok of ['', '30', '30s', '5m', '1h', '500ms', 10, null]) expect(isValidDelay(ok)).toBe(true)
    for (const ko of ['abc', '5d', '-3', '1h30']) expect(isValidDelay(ko)).toBe(false)
  })
})

describe('fallback (thread.yaml)', () => {
  it('forSave garde le fallback des workflows', async () => {
    const { forSave, fallbackNamesIn } = await import('./thread')
    const stages = [{ mode: 'sequential' as const, workflows: [
      { name: 'a', active: true, fallback: { use: ['a_backup'], when: "not source_available('db')", on_failure: true } },
      { name: 'b', active: true },
    ] }]
    expect(forSave(stages)[0].workflows[0].fallback).toEqual(stages[0].workflows[0].fallback)
    expect(fallbackNamesIn(stages)).toEqual(['a_backup'])
  })
})

describe('fallback — édition (Studio, étape 3)', () => {
  const T = (): ThreadStage[] => [
    { mode: 'sequential', workflows: [{ name: 'a', active: true }, { name: 'b', active: true }] },
    { mode: 'parallel', workflows: [{ name: 'c', active: true, fallback: { use: ['c_alt'], when: 'file_exists(\'x\')' } }] },
  ]
  it('candidats : ni lui-même, ni déjà choisi, ni un workflow qui a son propre fallback', async () => {
    const { fallbackCandidates } = await import('./thread')
    expect(fallbackCandidates(T(), ['a', 'b', 'c', 'c_alt', 'd'], 'a')).toEqual(['b', 'c_alt', 'd'])
    expect(fallbackCandidates(T(), ['a', 'b', 'c', 'c_alt', 'd'], 'c')).toEqual(['a', 'b', 'd'])
  })
  it('setFallback : un remplaçant du thread en sort ; null retire le fallback', async () => {
    const { setFallback, fallbackNamesIn } = await import('./thread')
    const s = setFallback(T(), 'a', { use: ['b'], when: "not source_available('db')" })
    expect(namesIn(s)).toEqual(['a', 'c'])
    expect(s[0].workflows[0].fallback?.use).toEqual(['b'])
    expect(fallbackNamesIn(s)).toEqual(['b', 'c_alt'])
    expect(setFallback(s, 'a', null)[0].workflows[0].fallback).toBeNull()
  })
  it('fallbackError : remplaçant et déclencheur obligatoires', async () => {
    const { fallbackError } = await import('./thread')
    expect(fallbackError(null)).toBeNull()
    expect(fallbackError({ use: [], when: 'x' })).toMatch(/replacement/)
    expect(fallbackError({ use: ['b'], when: '  ' })).toMatch(/condition/)
    expect(fallbackError({ use: ['b'], when: '', on_failure: true })).toBeNull()
  })
  it('forSave : valeurs par défaut retirées, fallback null supprimé', () => {
    const out = forSave([{ mode: 'sequential', workflows: [
      { name: 'a', active: true, fallback: { use: ['b'], when: ' file_exists(\'x\') ', on_failure: false, on_probe_error: 'keep' } },
      { name: 'c', active: true, fallback: null },
    ] }])
    expect(out[0].workflows[0].fallback).toEqual({ use: ['b'], when: "file_exists('x')" })
    expect('fallback' in out[0].workflows[1]).toBe(false)
  })
})

describe('delay_before (attente avant le lancement)', () => {
  it('forSave : gardé nettoyé, vide ou 0 retiré', () => {
    const out = forSave([{ mode: 'parallel', workflows: [
      { name: 'a', active: true, delay_before: ' 23s ' },
      { name: 'b', active: true, delay_before: '' },
      { name: 'c', active: true, delay_before: 0 },
      { name: 'd', active: true, delay_before: 2, fallback: { use: ['x'], when: "file_exists('f')" } },
    ] }])
    expect(out[0].workflows[0].delay_before).toBe('23s')
    expect('delay_before' in out[0].workflows[1]).toBe(false)
    expect('delay_before' in out[0].workflows[2]).toBe(false)
    expect(out[0].workflows[3]).toMatchObject({ delay_before: 2, fallback: { use: ['x'] } })
  })
  it('format validé comme delay_after', () => {
    for (const v of ['500ms', '30s', '5m', '1h', 2, '']) expect(isValidDelay(v)).toBe(true)
    for (const v of ['soon', '2x', '-1s']) expect(isValidDelay(v)).toBe(false)
  })
})

describe('timeout (durée maximale)', () => {
  it('validation : vide ou durée de plus de 0', () => {
    for (const ok of ['', '  ', '30s', '5m', '1h', '500ms', 10, null, undefined]) expect(isValidTimeout(ok)).toBe(true)
    for (const bad of ['0', '0s', 0, 'abc', '-5', '5 min']) expect(isValidTimeout(bad)).toBe(false)
  })
  it('forSave : vide retiré, espaces enlevés, gardé avec un fallback', () => {
    const out = forSave([{ mode: 'sequential', workflows: [
      { name: 'a', active: true, timeout: ' 30m ' },
      { name: 'b', active: true, timeout: '' },
      { name: 'c', active: true, timeout: '1h', fallback: { use: ['x'], on_failure: true } },
    ] }])
    expect(out[0].workflows[0].timeout).toBe('30m')
    expect('timeout' in out[0].workflows[1]).toBe(false)
    expect(out[0].workflows[2]).toMatchObject({ timeout: '1h', fallback: { use: ['x'], on_failure: true } })
  })
})
