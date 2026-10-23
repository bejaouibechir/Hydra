/**
 * Synchronisation d'un job entre le canvas de Studio et ses fichiers
 * jobs/<nom>/*.yaml sur le disque.
 *
 * Règle (Bechir, 23/10) : la dernière modification gagne, qu'elle vienne de
 * Studio ou de l'extérieur (éditeur, Bloc-notes, hdrctl, git).
 *
 *  - même contenu des deux côtés            → rien à faire
 *  - seul le disque a changé                 → Studio relit le disque
 *  - seul Studio a changé                    → Studio écrit sur le disque
 *  - les deux ont changé                     → la date la plus récente gagne
 *
 * « Contenu » = les 4 YAML tels que Studio les écrirait (forme canonique) :
 * une différence de mise en forme ou de commentaires n'est pas un changement.
 */
import type { Edge, Node } from '@xyflow/react'
import type { FlowNodeData } from './workflowSerializer'
import {
  flowToJobModel, jobModelToFlow, jobModelToSectionYamls, sectionYamlsToJobModel,
  type HydraJobModel, type JobSectionYamls,
} from './hdrSerializer'

export type SyncDecision = 'in_sync' | 'load_disk' | 'save_studio'

export interface SyncInput {
  /** le canvas et le disque décrivent le même job */
  same: boolean
  /** l'empreinte du disque a changé depuis la dernière synchronisation (ou jamais synchronisé) */
  diskChanged: boolean
  /** le canvas a changé depuis la dernière synchronisation : date de la dernière édition (ms), sinon null */
  studioEditAt: number | null
  /** date de dernière modification des fichiers (ms) */
  diskMtimeMs: number
}

export function decideSync({ same, diskChanged, studioEditAt, diskMtimeMs }: SyncInput): SyncDecision {
  if (same) return 'in_sync'
  if (studioEditAt === null) return diskChanged ? 'load_disk' : 'in_sync'
  if (!diskChanged) return 'save_studio'
  return diskMtimeMs > studioEditAt ? 'load_disk' : 'save_studio'
}

/** Forme canonique (4 YAML) d'un canvas de job. */
export function canonicalFromCanvas(nodes: Node[], edges: Edge[], jobName: string): string {
  try {
    const y = jobModelToSectionYamls(flowToJobModel(nodes as Node<FlowNodeData>[], edges, jobName))
    return [y.sources, y.transformations, y.destinations, y.pipeline].join('\n---\n')
  } catch {
    return ''
  }
}

/** Modèle + canvas reconstruits depuis les fichiers ; null si les YAML sont invalides. */
export function canvasFromDisk(files: JobSectionYamls, jobName: string):
  { model: HydraJobModel; nodes: Node<FlowNodeData>[]; edges: Edge[] } | null {
  if (!files.sources?.trim() && !files.destinations?.trim() && !files.pipeline?.trim()) return null
  const model = sectionYamlsToJobModel(files, jobName)
  if (!model) return null
  const { nodes, edges } = jobModelToFlow(model)
  return { model, nodes, edges }
}
