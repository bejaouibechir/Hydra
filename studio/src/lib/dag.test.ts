/**
 * dag.test.ts — Tests unitaires pour les utilitaires DAG
 * Lancer : npx vitest run src/lib/dag.test.ts
 */
import { describe, it, expect } from 'vitest'
import {
  hasCycle,
  topologicalSort,
  getRoots,
  getLeaves,
  computeLevels,
  validateDAG,
  edgesToDAGNodes,
  DAGNode,
} from './dag'

// ── Helpers ──────────────────────────────────────────────────────────────────

const n = (id: string, ...deps: string[]): DAGNode => ({ id, dependsOn: deps })

// ── hasCycle ─────────────────────────────────────────────────────────────────

describe('hasCycle', () => {
  it('retourne false pour un graphe vide', () => {
    expect(hasCycle([])).toBe(false)
  })

  it('retourne false pour un nœud seul sans dépendance', () => {
    expect(hasCycle([n('a')])).toBe(false)
  })

  it('retourne false pour une chaîne linéaire a→b→c', () => {
    expect(hasCycle([n('a'), n('b', 'a'), n('c', 'b')])).toBe(false)
  })

  it('retourne false pour un DAG en diamant (a→b, a→c, b→d, c→d)', () => {
    expect(hasCycle([n('a'), n('b', 'a'), n('c', 'a'), n('d', 'b', 'c')])).toBe(false)
  })

  it('détecte un cycle direct a→b→a', () => {
    expect(hasCycle([n('a', 'b'), n('b', 'a')])).toBe(true)
  })

  it('détecte un cycle indirect a→b→c→a', () => {
    expect(hasCycle([n('a', 'c'), n('b', 'a'), n('c', 'b')])).toBe(true)
  })

  it('détecte un auto-cycle (nœud dépend de lui-même)', () => {
    expect(hasCycle([n('a', 'a')])).toBe(true)
  })

  it('retourne false pour plusieurs racines indépendantes', () => {
    expect(hasCycle([n('a'), n('b'), n('c', 'a'), n('d', 'b')])).toBe(false)
  })
})

// ── topologicalSort ───────────────────────────────────────────────────────────

describe('topologicalSort', () => {
  it('retourne [] pour un graphe vide', () => {
    expect(topologicalSort([])).toEqual([])
  })

  it('retourne [a] pour un nœud seul', () => {
    expect(topologicalSort([n('a')])).toEqual(['a'])
  })

  it('ordonne une chaîne a→b→c dans le bon sens', () => {
    const result = topologicalSort([n('c', 'b'), n('a'), n('b', 'a')])
    expect(result.indexOf('a')).toBeLessThan(result.indexOf('b'))
    expect(result.indexOf('b')).toBeLessThan(result.indexOf('c'))
  })

  it('diamant : a avant b et c, b et c avant d', () => {
    const result = topologicalSort([n('d', 'b', 'c'), n('b', 'a'), n('c', 'a'), n('a')])
    expect(result.indexOf('a')).toBeLessThan(result.indexOf('b'))
    expect(result.indexOf('a')).toBeLessThan(result.indexOf('c'))
    expect(result.indexOf('b')).toBeLessThan(result.indexOf('d'))
    expect(result.indexOf('c')).toBeLessThan(result.indexOf('d'))
  })

  it('retourne tous les nœuds (même longueur)', () => {
    const nodes = [n('a'), n('b', 'a'), n('c', 'a'), n('d', 'b', 'c')]
    expect(topologicalSort(nodes)).toHaveLength(4)
  })

  it('lève une erreur si cycle détecté', () => {
    expect(() => topologicalSort([n('a', 'b'), n('b', 'a')])).toThrow()
  })

  it('lève une erreur si dépendance inconnue', () => {
    expect(() => topologicalSort([n('a', 'inexistant')])).toThrow(/inexistant/)
  })

  it('graphe en éventail : plusieurs racines indépendantes', () => {
    const nodes = [n('root1'), n('root2'), n('child', 'root1', 'root2')]
    const result = topologicalSort(nodes)
    expect(result.indexOf('root1')).toBeLessThan(result.indexOf('child'))
    expect(result.indexOf('root2')).toBeLessThan(result.indexOf('child'))
  })

  it('est stable (même entrée → même sortie)', () => {
    const nodes = [n('b', 'a'), n('a'), n('c', 'a')]
    const r1 = topologicalSort(nodes)
    const r2 = topologicalSort(nodes)
    expect(r1).toEqual(r2)
  })
})

// ── getRoots / getLeaves ──────────────────────────────────────────────────────

describe('getRoots', () => {
  it('retourne les nœuds sans dépendances', () => {
    const roots = getRoots([n('a'), n('b', 'a'), n('c')])
    expect(roots.map(r => r.id).sort()).toEqual(['a', 'c'])
  })

  it('retourne [] si tous les nœuds ont des dépendances (cycle)', () => {
    expect(getRoots([n('a', 'b'), n('b', 'a')])).toEqual([])
  })
})

describe('getLeaves', () => {
  it('retourne les nœuds dont personne ne dépend', () => {
    const leaves = getLeaves([n('a'), n('b', 'a'), n('c', 'b')])
    expect(leaves.map(l => l.id)).toEqual(['c'])
  })

  it('graphe en diamant : seul d est feuille', () => {
    const leaves = getLeaves([n('a'), n('b', 'a'), n('c', 'a'), n('d', 'b', 'c')])
    expect(leaves.map(l => l.id)).toEqual(['d'])
  })

  it('nœud seul est à la fois racine et feuille', () => {
    const leaves = getLeaves([n('a')])
    expect(leaves.map(l => l.id)).toEqual(['a'])
  })
})

// ── computeLevels ─────────────────────────────────────────────────────────────

describe('computeLevels', () => {
  it('racine seule est au niveau 0', () => {
    const levels = computeLevels([n('a')])
    expect(levels.get('a')).toBe(0)
  })

  it('chaîne a→b→c : niveaux 0, 1, 2', () => {
    const levels = computeLevels([n('a'), n('b', 'a'), n('c', 'b')])
    expect(levels.get('a')).toBe(0)
    expect(levels.get('b')).toBe(1)
    expect(levels.get('c')).toBe(2)
  })

  it('diamant : d au niveau 2', () => {
    const levels = computeLevels([n('a'), n('b', 'a'), n('c', 'a'), n('d', 'b', 'c')])
    expect(levels.get('a')).toBe(0)
    expect(levels.get('b')).toBe(1)
    expect(levels.get('c')).toBe(1)
    expect(levels.get('d')).toBe(2)
  })

  it('lève une erreur si cycle', () => {
    expect(() => computeLevels([n('a', 'b'), n('b', 'a')])).toThrow()
  })
})

// ── validateDAG ───────────────────────────────────────────────────────────────

describe('validateDAG', () => {
  it('valide un DAG correct', () => {
    const result = validateDAG([n('a'), n('b', 'a'), n('c', 'b')])
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  it('détecte un ID dupliqué', () => {
    const result = validateDAG([n('a'), n('a', 'b'), n('b')])
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.includes('Duplicate'))).toBe(true)
  })

  it('détecte une référence inconnue', () => {
    const result = validateDAG([n('a', 'fantome')])
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.includes('fantome'))).toBe(true)
  })

  it('détecte un cycle', () => {
    const result = validateDAG([n('a', 'b'), n('b', 'a')])
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.includes('cycle'))).toBe(true)
  })

  it('graphe vide est valide', () => {
    expect(validateDAG([]).valid).toBe(true)
  })

  it('nœud isolé dans un graphe multi-nœuds → signalé comme unreachable', () => {
    const result = validateDAG([n('a'), n('b'), n('c', 'b')])
    // 'a' est racine et feuille (isolé dans ce contexte)
    expect(result.unreachable).toContain('a')
  })
})

// ── edgesToDAGNodes ───────────────────────────────────────────────────────────

describe('edgesToDAGNodes', () => {
  it('convertit des edges React Flow en DAGNodes', () => {
    const nodes = edgesToDAGNodes(
      ['a', 'b', 'c'],
      [{ source: 'a', target: 'b' }, { source: 'a', target: 'c' }]
    )
    const b = nodes.find(n => n.id === 'b')!
    const c = nodes.find(n => n.id === 'c')!
    const a = nodes.find(n => n.id === 'a')!
    expect(b.dependsOn).toEqual(['a'])
    expect(c.dependsOn).toEqual(['a'])
    expect(a.dependsOn).toEqual([])
  })

  it('retourne [] pour des edges vides', () => {
    const nodes = edgesToDAGNodes(['a', 'b'], [])
    expect(nodes.every(n => n.dependsOn.length === 0)).toBe(true)
  })

  it('produit un tri topologique valide après conversion', () => {
    const dagNodes = edgesToDAGNodes(
      ['start', 'extract', 'transform', 'load'],
      [
        { source: 'start', target: 'extract' },
        { source: 'extract', target: 'transform' },
        { source: 'transform', target: 'load' },
      ]
    )
    const order = topologicalSort(dagNodes)
    expect(order).toEqual(['start', 'extract', 'transform', 'load'])
  })
})

// ── Cas limites ───────────────────────────────────────────────────────────────

describe('cas limites', () => {
  it('graphe large sans cycle (50 nœuds en chaîne)', () => {
    const nodes: DAGNode[] = [{ id: 'n0', dependsOn: [] }]
    for (let i = 1; i < 50; i++) {
      nodes.push({ id: `n${i}`, dependsOn: [`n${i - 1}`] })
    }
    expect(hasCycle(nodes)).toBe(false)
    const order = topologicalSort(nodes)
    expect(order).toHaveLength(50)
    expect(order[0]).toBe('n0')
    expect(order[49]).toBe('n49')
  })

  it('fan-out extrême : 1 racine → 10 feuilles', () => {
    const nodes: DAGNode[] = [n('root')]
    for (let i = 0; i < 10; i++) nodes.push(n(`leaf${i}`, 'root'))
    expect(hasCycle(nodes)).toBe(false)
    const order = topologicalSort(nodes)
    expect(order[0]).toBe('root')
    expect(getLeaves(nodes)).toHaveLength(10)
  })
})
