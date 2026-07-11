/**
 * dag.ts — Utilitaires de graphe orienté acyclique (DAG)
 * Utilisé pour valider et ordonner les steps d'un workflow Hydra.
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface DAGNode {
  id: string
  /** IDs des nœuds dont ce nœud dépend (parents directs) */
  dependsOn: string[]
}

export interface DAGEdge {
  source: string
  target: string
}

export interface DAGValidationResult {
  valid: boolean
  errors: string[]
  /** Nœuds inaccessibles depuis les racines */
  unreachable: string[]
}

// ── Helpers internes ─────────────────────────────────────────────────────────

/** Construit un mapping id → nœud pour accès O(1) */
function buildIndex(nodes: DAGNode[]): Map<string, DAGNode> {
  return new Map(nodes.map(n => [n.id, n]))
}

/** Construit la liste d'adjacence (parent → enfants) */
function buildAdjacency(nodes: DAGNode[]): Map<string, string[]> {
  const adj = new Map<string, string[]>(nodes.map(n => [n.id, []]))
  for (const node of nodes) {
    for (const dep of node.dependsOn) {
      const children = adj.get(dep)
      if (children) children.push(node.id)
    }
  }
  return adj
}

// ── API publique ─────────────────────────────────────────────────────────────

/**
 * Détecte si le graphe contient un cycle.
 * Algorithme : DFS avec coloriage (blanc/gris/noir).
 * @returns true si un cycle est présent
 */
export function hasCycle(nodes: DAGNode[]): boolean {
  const WHITE = 0, GRAY = 1, BLACK = 2
  const color = new Map<string, number>(nodes.map(n => [n.id, WHITE]))

  function dfs(id: string): boolean {
    color.set(id, GRAY)
    const node = nodes.find(n => n.id === id)
    if (!node) return false
    for (const dep of node.dependsOn) {
      const c = color.get(dep)
      if (c === GRAY) return true            // back-edge → cycle
      if (c === WHITE && dfs(dep)) return true
    }
    color.set(id, BLACK)
    return false
  }

  for (const node of nodes) {
    if (color.get(node.id) === WHITE && dfs(node.id)) return true
  }
  return false
}

/**
 * Tri topologique (ordre d'exécution).
 * Les nœuds sans dépendances (racines) viennent en premier.
 * Algorithme : Kahn (BFS, in-degree).
 * @throws Error si le graphe contient un cycle
 * @returns Liste ordonnée d'IDs
 */
export function topologicalSort(nodes: DAGNode[]): string[] {
  if (nodes.length === 0) return []

  const index = buildIndex(nodes)
  const inDegree = new Map<string, number>(nodes.map(n => [n.id, 0]))

  // Calculer in-degree de chaque nœud
  for (const node of nodes) {
    for (const dep of node.dependsOn) {
      if (!index.has(dep)) {
        throw new Error(`Dépendance inconnue : "${dep}" référencée par "${node.id}"`)
      }
      inDegree.set(node.id, (inDegree.get(node.id) ?? 0) + 1)
    }
  }

  // Kahn : file des nœuds avec in-degree = 0 (racines)
  const queue: string[] = []
  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id)
  }
  // Tri stable : ordre alphabétique pour les racines à même niveau
  queue.sort()

  const adj = buildAdjacency(nodes)
  const result: string[] = []

  while (queue.length > 0) {
    // Prend le premier (déjà trié)
    const id = queue.shift()!
    result.push(id)

    const children = (adj.get(id) ?? []).slice().sort()
    for (const child of children) {
      const newDeg = (inDegree.get(child) ?? 0) - 1
      inDegree.set(child, newDeg)
      if (newDeg === 0) {
        // Insertion triée pour ordre stable
        const pos = queue.findIndex(q => q > child)
        pos === -1 ? queue.push(child) : queue.splice(pos, 0, child)
      }
    }
  }

  if (result.length !== nodes.length) {
    throw new Error('Cycle détecté — tri topologique impossible')
  }

  return result
}

/**
 * Retourne les nœuds racines (sans dépendances).
 */
export function getRoots(nodes: DAGNode[]): DAGNode[] {
  return nodes.filter(n => n.dependsOn.length === 0)
}

/**
 * Retourne les nœuds feuilles (aucun autre nœud ne dépend d'eux).
 */
export function getLeaves(nodes: DAGNode[]): DAGNode[] {
  const hasChildren = new Set<string>()
  for (const n of nodes) {
    for (const dep of n.dependsOn) hasChildren.add(dep)
  }
  return nodes.filter(n => !hasChildren.has(n.id))
}

/**
 * Calcule le niveau (profondeur) de chaque nœud dans le DAG.
 * Racines = niveau 0. Utilisé pour le layout automatique.
 */
export function computeLevels(nodes: DAGNode[]): Map<string, number> {
  const order = topologicalSort(nodes) // lève si cycle
  const index = buildIndex(nodes)
  const levels = new Map<string, number>()

  for (const id of order) {
    const node = index.get(id)!
    if (node.dependsOn.length === 0) {
      levels.set(id, 0)
    } else {
      const maxParentLevel = Math.max(...node.dependsOn.map(dep => levels.get(dep) ?? 0))
      levels.set(id, maxParentLevel + 1)
    }
  }

  return levels
}

/**
 * Validation complète du DAG.
 * Vérifie : doublons d'ID, références inconnues, cycles, nœuds isolés.
 */
export function validateDAG(nodes: DAGNode[]): DAGValidationResult {
  const errors: string[] = []
  const unreachable: string[] = []

  // Doublons
  const ids = nodes.map(n => n.id)
  const seen = new Set<string>()
  for (const id of ids) {
    if (seen.has(id)) errors.push(`ID dupliqué : "${id}"`)
    seen.add(id)
  }

  // Références inconnues
  const idSet = new Set(ids)
  for (const node of nodes) {
    for (const dep of node.dependsOn) {
      if (!idSet.has(dep)) {
        errors.push(`"${node.id}" dépend de "${dep}" qui n'existe pas`)
      }
    }
  }

  // Cycle
  if (hasCycle(nodes)) {
    errors.push('Le graphe contient un cycle')
  }

  // Nœuds isolés (sans dépendances et sans enfants) — warning, pas erreur
  if (nodes.length > 1) {
    const hasChildren = new Set<string>()
    for (const n of nodes) {
      for (const dep of n.dependsOn) hasChildren.add(dep)
    }
    for (const n of nodes) {
      if (n.dependsOn.length === 0 && !hasChildren.has(n.id)) {
        unreachable.push(n.id)
      }
    }
  }

  return { valid: errors.length === 0, errors, unreachable }
}

/**
 * Convertit des edges React Flow en DAGNodes.
 * Chaque edge { source, target } signifie : target dépend de source.
 */
export function edgesToDAGNodes(
  nodeIds: string[],
  edges: DAGEdge[]
): DAGNode[] {
  const depMap = new Map<string, string[]>(nodeIds.map(id => [id, []]))
  for (const { source, target } of edges) {
    const deps = depMap.get(target)
    if (deps) deps.push(source)
  }
  return nodeIds.map(id => ({ id, dependsOn: depMap.get(id) ?? [] }))
}
