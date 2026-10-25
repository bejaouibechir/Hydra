import { describe, it, expect } from 'vitest'
import { appendWorkflow, forSave, isValidDelay, moveWorkflow, namesIn, removeWorkflow, type ThreadStage } from './thread'

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
