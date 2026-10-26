import { describe, it, expect } from 'vitest'
import { layoutThread, NODE_H, NODE_W } from './threadLayout'
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

describe('layoutThread — fallback', () => {
  const fb: ThreadStage[] = [
    { mode: 'sequential', workflows: [{ name: 'a', active: true, fallback: { use: ['a1', 'a2'], when: "not source_available('crm')" } }] },
    { mode: 'parallel', workflows: [{ name: 'b', active: true, fallback: { use: ['b1'], on_failure: true } }, { name: 'c', active: true }] },
  ]
  it('remplaçants sous leur workflow, même colonne, condition sur le trait', () => {
    const l = layoutThread(fb)
    const n = (id: string) => l.nodes.find(x => x.id === id)!
    expect(n('a>a1').fallbackOf).toBe('a')
    expect(n('a>a1').col).toBe(n('a').col)
    expect(n('a>a1').y).toBeGreaterThan(n('a').y + NODE_H)
    expect(n('a>a2').y).toBeGreaterThan(n('a>a1').y)
    expect(n('c').y).toBeGreaterThan(n('b>b1').y)              // parallèle : c sous le remplaçant de b
    expect(l.fallbacks.filter(f => f.of === 'a')).toHaveLength(2)
    expect(l.fallbacks[0].label).toMatch(/^if not source_avail/)
    expect(l.fallbacks.find(f => f.of === 'b')!.label).toBe('on failure')
    // flèches d'arrivée et jonctions : seulement les workflows du thread
    expect(l.edges).toHaveLength(1 + 2)
    expect(l.height).toBeGreaterThan(Math.max(...l.nodes.map(x => x.y + x.h)))
  })
})

describe('layoutThread — delay_before', () => {
  it('horloge sur les workflows qui attendent', () => {
    const l = layoutThread([{ mode: 'parallel', workflows: [
      { name: 'a', active: true }, { name: 'b', active: true, delay_before: 23 }, { name: 'c', active: true, delay_before: '500ms' },
    ] }])
    const w = (n: string) => l.nodes.find(x => x.name === n)!.wait
    expect([w('a'), w('b'), w('c')]).toEqual([null, '23s', '500ms'])
  })
})
