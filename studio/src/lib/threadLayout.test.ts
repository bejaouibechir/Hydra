import { describe, it, expect } from 'vitest'
import { layoutThread, NODE_W } from './threadLayout'
import { loopErrors, pruneLoops, threadUnits, type ThreadStage } from './thread'

const stages: ThreadStage[] = [
  { mode: 'sequential', delay_after: '1s', workflows: [{ name: 'w1', active: true }] },
  { mode: 'parallel', delay_after: '', workflows: [{ name: 'w2', active: true }, { name: 'w3', active: false }] },
  { mode: 'parallel', workflows: [{ name: 'w4', active: true }, { name: 'w5', active: true }] },
]

describe('threadUnits / loopErrors', () => {
  it('découpe comme le moteur', () => {
    expect(threadUnits(stages).map(u => u.names)).toEqual([['w1'], ['w2', 'w3'], ['w4', 'w5']])
  })
  it('valide les boucles', () => {
    expect(loopErrors(stages, [
      { from: 'w5', to: 'w1', times: 3 },
      { from: 'w1', to: 'w5', times: 2 },
      { from: 'w9', to: 'w1', times: 2 },
      { from: 'w4', to: 'w4', times: 0 },
    ])).toEqual([null, "'w5' must come before 'w1' (a loop goes back)", "'w9' is not in the thread", 'times: 1 to 1000'])
    expect(loopErrors(stages, [{ from: 'w3', to: 'w1', times: 2 }, { from: 'w5', to: 'w2', times: 2 }])[1]).toBe('overlaps another loop')
  })
  it('retire les boucles orphelines', () => {
    expect(pruneLoops(stages.slice(0, 1), [{ from: 'w5', to: 'w1', times: 2 }])).toEqual([])
  })
})

describe('layoutThread', () => {
  it('une colonne par unité, parallèles empilés, losange si délai', () => {
    const l = layoutThread(stages, [{ from: 'w5', to: 'w1', times: 3, delay: '5m' }])
    const col = (n: string) => l.nodes.find(x => x.name === n)!
    expect(col('w2').x).toBe(col('w3').x)
    expect(col('w2').y).toBeLessThan(col('w3').y)
    expect(col('w4').x).toBeGreaterThan(col('w2').x + NODE_W)
    expect(col('w3').active).toBe(false)
    expect(l.junctions.map(j => j.delay)).toEqual(['1s', null])
    expect(l.loops).toHaveLength(1)
    expect(l.loops[0]).toMatchObject({ times: 3, delay: '5m' })
    expect(l.height).toBeGreaterThan(Math.max(...l.nodes.map(n => n.y)))
    expect(l.width).toBeGreaterThan(col('w5').x)
  })
  it('thread vide', () => {
    const l = layoutThread([])
    expect(l.nodes).toEqual([]); expect(l.edges).toEqual([])
  })
})
