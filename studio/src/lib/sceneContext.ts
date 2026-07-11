import { createContext } from 'react'

export type SceneMode = 'jobs' | 'workflow'

/**
 * Scène courante de l'éditeur, exposée aux nœuds React Flow (HydraNode)
 * afin qu'ils adaptent leur UI (ex : masquer « Execute step » en Jobs Configuration).
 */
export const SceneContext = createContext<SceneMode>('workflow')
