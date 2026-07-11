/**
 * useUndoRedo — Historique undo/redo pour le canvas React Flow.
 *
 * Modèle past / present / future :
 *   push(nodes, edges)            → sauvegarde l'état courant avant une action
 *   undo(currentNodes, currentEdges) → restaure le précédent, mémorise le courant pour redo
 *   redo(currentNodes, currentEdges) → rejoue l'annulé, mémorise le courant pour undo
 *
 * MAX_HISTORY snapshots conservés (FIFO).
 */
import { useRef, useState, useCallback } from 'react'
import type { Node, Edge } from '@xyflow/react'

const MAX_HISTORY = 50

interface Snapshot {
  nodes: Node[]
  edges: Edge[]
}

function clone(nodes: Node[], edges: Edge[]): Snapshot {
  return {
    nodes: JSON.parse(JSON.stringify(nodes)),
    edges: JSON.parse(JSON.stringify(edges)),
  }
}

export function useUndoRedo() {
  const past   = useRef<Snapshot[]>([])
  const future = useRef<Snapshot[]>([])
  const [flags, setFlags] = useState({ canUndo: false, canRedo: false })

  const sync = useCallback(() => {
    setFlags({ canUndo: past.current.length > 0, canRedo: future.current.length > 0 })
  }, [])

  /**
   * Sauvegarde l'état courant dans le passé.
   * Efface le futur (toute action brise la chaîne redo).
   */
  const push = useCallback((nodes: Node[], edges: Edge[]) => {
    past.current.push(clone(nodes, edges))
    if (past.current.length > MAX_HISTORY) past.current.shift()
    future.current = []
    sync()
  }, [sync])

  /**
   * Annule la dernière action.
   * Sauvegarde l'état courant dans le futur pour permettre redo.
   * Retourne le snapshot à restaurer, ou null si rien à annuler.
   */
  const undo = useCallback((currentNodes: Node[], currentEdges: Edge[]): Snapshot | null => {
    const prev = past.current.pop()
    if (!prev) return null
    future.current.push(clone(currentNodes, currentEdges))
    sync()
    return prev
  }, [sync])

  /**
   * Rejoue l'action annulée.
   * Sauvegarde l'état courant dans le passé.
   * Retourne le snapshot à restaurer, ou null si rien à refaire.
   */
  const redo = useCallback((currentNodes: Node[], currentEdges: Edge[]): Snapshot | null => {
    const next = future.current.pop()
    if (!next) return null
    past.current.push(clone(currentNodes, currentEdges))
    sync()
    return next
  }, [sync])

  return { push, undo, redo, canUndo: flags.canUndo, canRedo: flags.canRedo }
}
