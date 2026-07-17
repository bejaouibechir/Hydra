/**
 * WorkflowEditor — Canvas React Flow pour éditer un workflow Hydra.
 * Route : /workflows/:workflowId?projectId=...
 */
import { useCallback, useRef, useState, useEffect, useMemo } from 'react'
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow, ReactFlowProvider, Background, Controls, MiniMap,
  addEdge, useNodesState, useEdgesState,
  type Node, type Edge, type Connection, type ReactFlowInstance,
  BackgroundVariant, MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import * as YAML from 'js-yaml'
import { api, type Run } from '@/lib/api'
import { validateDAG, edgesToDAGNodes } from '@/lib/dag'
import { flowToWorkflow, workflowToYAMLString, workflowToFlow, parseWorkflowYAML, isContainerNode, isProxyEdge, CONTAINER_NODE_TYPE, type FlowNodeData } from '@/lib/workflowSerializer'
import { flowToHdr, parseHdr, sectionYamlsToJobModel, jobModelToFlow, flowToJobModel, jobModelToSectionYamls, type JobSectionYamls } from '@/lib/hdrSerializer'
import type { JobFilesPayload } from '@/lib/api'
import { getNode } from '@/lib/nodeRegistry'
import { HydraNode } from '@/components/canvas/nodes/HydraNode'
import { ContainerNode } from '@/components/canvas/nodes/ContainerNode'
import { applyCollapsedState, attachNodeToContainer, detachNode, isDescendant } from '@/lib/containers'
import NodePalette from '@/components/canvas/NodePalette'
import CanvasToolbox, { type InteractionMode } from '@/components/canvas/CanvasToolbox'
import PropertiesPanel from '@/components/canvas/PropertiesPanel'
import NodeContextMenu, { type ContextMenuState } from '@/components/canvas/NodeContextMenu'
import NodeConfigDialog from '@/components/canvas/NodeConfigDialog'
import YamlCodePanel from '@/components/canvas/YamlCodePanel'
import TerminalPanel from '@/components/canvas/TerminalPanel'
import ParametersPanel from '@/components/canvas/ParametersPanel'
import LogViewer from '@/components/ui/LogViewer'
import Spinner from '@/components/ui/Spinner'
import {
  Save, Play, ChevronLeft, AlertTriangle, CheckCircle2, GitBranch,
  ChevronDown, ChevronUp, Terminal, Circle, Code2, Upload,
  Undo2, Redo2, Trash2, FolderOpen, Package, MoreHorizontal,
  Pencil, Copy, ArrowLeft, Archive, Boxes,
} from 'lucide-react'
import { useUndoRedo } from '@/hooks/useUndoRedo'
import { loadSettings } from '@/pages/Settings'
import { SceneContext } from '@/lib/sceneContext'

// ── React Flow custom node types ─────────────────────────────────────────────

const NODE_TYPES = { hydraNode: HydraNode, container: ContainerNode }

// Dimensions par défaut d'un conteneur nouvellement créé + marge intérieure
const CONTAINER_DEFAULT_W = 320
const CONTAINER_DEFAULT_H = 220
const CONTAINER_PAD = 40        // marge autour des nœuds enfants lors d'un « grouper »
const CONTAINER_HEADER_H = 44   // hauteur de la barre de titre (zone non-drop haute)

// ── Helpers ──────────────────────────────────────────────────────────────────

let _idCounter = 1
function newNodeId(type: string) { return `${type}_${_idCounter++}` }

/** Slug sûr pour noms de dossiers/fichiers — miroir de _slug() côté backend */
function slugify(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_-]/g, '') || 'unnamed'
}

/** Sérialise chaque job canvas en 4 YAML — matérialisés sur disk par le backend */
function buildJobsPayload(
  canvases: Record<string, { nodes: Node[]; edges: Edge[] }>,
  names: Map<string, string>,
): JobFilesPayload[] {
  return Object.entries(canvases)
    .filter(([, c]) => (c.nodes?.length ?? 0) > 0)
    .map(([jid, c]) => {
      const jobName = slugify(names.get(jid) ?? jid)
      const model   = flowToJobModel(c.nodes as Node<FlowNodeData>[], c.edges, jobName)
      const y       = jobModelToSectionYamls(model)
      return { name: jobName, sources: y.sources, transformations: y.transformations, destinations: y.destinations, pipeline: y.pipeline }
    })
}

/** Résout un paramètre ?jobId= vers la clé de canvas : accepte l'id interne,
 *  le nom affiché du job, ou son slug (liens des notifications). */
function resolveJobKey(names: Map<string, string>, wanted: string | null): string | null {
  if (!wanted) return null
  if (names.has(wanted)) return wanted
  for (const [key, name] of names) {
    if (name === wanted || slugify(name) === wanted) return key
  }
  return null
}

/** Nettoie un canvas venant du disk/backend : ne garde que les nœuds/edges
 *  structurellement valides — un layout corrompu ne doit JAMAIS crasher le rendu. */
function sanitizeCanvas(rawNodes?: unknown, rawEdges?: unknown): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  const nodes = (Array.isArray(rawNodes) ? rawNodes : []).filter((n): n is Node<FlowNodeData> => {
    const x = n as { id?: unknown; position?: { x?: unknown; y?: unknown }; data?: unknown } | null
    return Boolean(
      x && typeof x.id === 'string' &&
      x.position && Number.isFinite(x.position.x) && Number.isFinite(x.position.y) &&
      x.data && typeof x.data === 'object'
    )
  })
  const ids = new Set(nodes.map(n => n.id))
  const edges = (Array.isArray(rawEdges) ? rawEdges : []).filter((e): e is Edge => {
    const x = e as { source?: unknown; target?: unknown } | null
    return Boolean(x && typeof x.source === 'string' && typeof x.target === 'string'
      && ids.has(x.source) && ids.has(x.target))
  })
  // Purge des parentId orphelins (conteneur supprimé hors Studio) + ordre parent-avant-enfant.
  const cleaned = nodes.map(n => {
    const pid = (n as { parentId?: unknown }).parentId
    if (typeof pid === 'string' && !ids.has(pid)) {
      const { parentId: _p, extent: _e, ...rest } = n as Node<FlowNodeData> & { extent?: unknown }
      return rest as Node<FlowNodeData>
    }
    return n
  })
  // Rejoue l'état replié des conteneurs (nettoie + reconstruit les proxies).
  return applyCollapsedState(reorderParentsFirst(cleaned), edges)
}

/** React Flow exige qu'un nœud parent précède ses enfants dans le tableau.
 *  Nesting simple v1 : racines (sans parentId) d'abord, enfants ensuite. */
function reorderParentsFirst(ns: Node<FlowNodeData>[]): Node<FlowNodeData>[] {
  const roots    = ns.filter(n => !(n as { parentId?: unknown }).parentId)
  const children = ns.filter(n => (n as { parentId?: unknown }).parentId)
  return children.length ? [...roots, ...children] : ns
}

/** Injecte jobPath + stepName lisible sur les nœuds job avant sérialisation workflow.yaml */
function withJobPaths(wfNodes: Node<FlowNodeData>[], names: Map<string, string>): Node<FlowNodeData>[] {
  const used = new Map<string, number>()
  return wfNodes.map(n => {
    const d = n.data as FlowNodeData
    if (d.nodeType !== 'job') return n
    const jid   = ((d as Record<string, unknown>).jobRef as string) ?? n.id
    const base  = slugify(names.get(jid) ?? d.stepName ?? jid)
    const count = used.get(base) ?? 0
    used.set(base, count + 1)
    const stepName = d.stepName?.trim() ? d.stepName : (count === 0 ? base : `${base}_${count + 1}`)
    const jobPath  = d.jobPath?.trim() ? d.jobPath : `../jobs/${base}`
    return { ...n, data: { ...d, stepName, jobPath } }
  })
}

function makeFlowNode(nodeType: string, position: { x: number; y: number }): Node<FlowNodeData> {
  const def      = getNode(nodeType)
  const id       = newNodeId(nodeType)
  const isAction = def?.category === 'action'
  return {
    id,
    type: 'hydraNode',
    position,
    data: {
      label:    def?.label ?? nodeType,
      nodeType,
      stepName: id,
      jobPath:  isAction ? undefined : '',
      action:   isAction ? def?.type.replace('action_', '') : undefined,
      onFailure: 'fail',
      enabled:   true,
    },
  }
}

const DEST_TYPE: Record<string, string> = {
  dest_csv: 'csv', dest_json: 'json', dest_parquet: 'parquet',
  dest_mysql: 'mysql', dest_postgres: 'postgresql', dest_mongodb: 'mongodb',
}

// ── DataViewerModal — visionneuse top N (lecture directe de la destination) ──

function DataViewerModal({ rows, cols, loading, error, limitRows, onClose }: {
  rows: Record<string, unknown>[]
  cols: string[]
  loading: boolean
  error: string | null
  limitRows: number
  onClose: () => void
}) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 9998, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 'min(860px, 92vw)', maxHeight: '82vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', border: '1px solid var(--bg-border)', borderRadius: 12, boxShadow: '0 12px 40px rgba(0,0,0,0.5)', overflow: 'hidden' }}>
        <div className="flex items-center gap-2 px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--bg-border)' }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--primary)', fontFamily: 'monospace', letterSpacing: 1 }}>DONNÉES DE SORTIE</span>
          <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>top {limitRows}</span>
          <div className="flex-1" />
          <button onClick={onClose} className="btn-secondary text-xs !py-0.5">✕</button>
        </div>
        <div className="flex-1 overflow-auto" style={{ fontSize: 11 }}>
          {loading ? (
            <div className="flex items-center justify-center" style={{ height: 160, color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: 12 }}>Lecture de la destination…</div>
          ) : error ? (
            <div className="flex items-center justify-center px-4 text-center" style={{ height: 160, color: 'var(--error)', fontFamily: 'monospace', fontSize: 12 }}>{error}</div>
          ) : rows.length === 0 ? (
            <div className="flex items-center justify-center" style={{ height: 160, color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: 12 }}>Aucune donnée dans la destination.</div>
          ) : (
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 'max-content' }}>
              <thead>
                <tr style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 2 }}>
                  <th style={{ padding: '4px 10px', borderBottom: '2px solid var(--bg-border)', color: 'var(--text-muted)', fontWeight: 700, textAlign: 'center', minWidth: 36, fontSize: 10 }}>#</th>
                  {cols.map(col => (
                    <th key={col} style={{ padding: '4px 12px', borderBottom: '2px solid var(--bg-border)', color: 'var(--primary)', fontWeight: 700, textAlign: 'left', whiteSpace: 'nowrap', fontFamily: 'monospace' }}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri} style={{ background: ri % 2 === 0 ? 'transparent' : 'var(--bg-hover)' }}>
                    <td style={{ padding: '3px 10px', color: 'var(--text-muted)', textAlign: 'center', fontFamily: 'monospace', fontSize: 10 }}>{ri + 1}</td>
                    {cols.map(col => (
                      <td key={col} style={{ padding: '3px 12px', whiteSpace: 'nowrap', fontFamily: 'monospace', color: 'var(--text-secondary)', borderBottom: '1px solid var(--bg-border)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }} title={String(row[col] ?? '')}>
                        {row[col] == null ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>null</span> : String(row[col])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

function WorkflowEditorInner() {
  const { workflowId }  = useParams<{ workflowId: string }>()
  const [sp, setSp]     = useSearchParams()
  const projectId       = sp.get('projectId') ?? ''
  const qc              = useQueryClient()
  const rfWrapper          = useRef<HTMLDivElement>(null)
  const importInputRef     = useRef<HTMLInputElement>(null)   // legacy .hdr
  const importFolderRef    = useRef<HTMLInputElement>(null)   // dossier job
  const [importMenuOpen, setImportMenuOpen] = useState(false)
  // Chemin absolu du dossier importé — utilisé comme work_dir pour résoudre les chemins relatifs
  const [importedJobPath, setImportedJobPath] = useState<string | undefined>(undefined)
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null)
  useEffect(() => { rfInstanceRef.current = rfInstance }, [rfInstance])

  /** Recentre la vue sur les nœuds chargés — l'utilisateur ne doit JAMAIS
   *  avoir à chercher son canvas hors champ. Retry tant que React Flow
   *  n'est pas initialisé (chargements asynchrones). */
  const fitViewSoon = useCallback((delay = 80) => {
    const attemptFit = (n: number) => {
      const inst = rfInstanceRef.current
      if (inst) inst.fitView({ padding: 0.18, duration: 300, maxZoom: 1.15 })
      else if (n < 12) setTimeout(() => attemptFit(n + 1), 100)
    }
    setTimeout(() => attemptFit(0), delay)
  }, [])

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNode, setSelectedNode]  = useState<Node<FlowNodeData> | null>(null)
  const [saveStatus, setSaveStatus]      = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  // Flag : évite l'auto-save pendant le chargement initial
  const canAutoSave = useRef(false)
  // Workflow déjà initialisé (évite de réinitialiser scène/canvas à chaque refetch)
  const initializedWfRef = useRef<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  // Erreurs de manifests détectées au chargement : « fichier — ligne N : message »
  const [loadIssues, setLoadIssues] = useState<string[]>([])
  const [contextMenu, setContextMenu]    = useState<ContextMenuState | null>(null)
  const [renameNodeId, setRenameNodeId]  = useState<string | null>(null)
  // Mode "replace" — nodeId en attente de remplacement
  const [replaceNodeId, setReplaceNodeId] = useState<string | null>(null)
  // Modale de configuration
  const [dialogNode, setDialogNode] = useState<Node<FlowNodeData> | null>(null)
  // Logs panel
  const [logsOpen, setLogsOpen]   = useState(false)
  const [logsPanelH, setLogsPanelH] = useState(280)
  const [lastRun, setLastRun]     = useState<Run | null>(null)
  // YAML code panel
  const [codeOpen, setCodeOpen]   = useState(false)
  // Panneau Output (latéral droit)
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewer, setViewer] = useState<{ loading: boolean; error: string | null; cols: string[]; rows: Record<string, unknown>[] }>({ loading: false, error: null, cols: [], rows: [] })
  // Terminal intégré (bash / powershell)
  const [terminalShell, setTerminalShell] = useState<'powershell' | 'bash' | 'ssh' | null>(null)
  const [bottomTab, setBottomTab] = useState<'logs' | 'params' | 'terminal'>('logs')
  const { data: sysInfo } = useQuery({ queryKey: ['system-info'], queryFn: api.system.info, staleTime: Infinity })
  const defaultShell: 'powershell' | 'bash' = sysInfo?.is_windows ? 'powershell' : 'bash'

  // ── Two-level canvas : Workflow ↔ Job ────────────────────────────────────
  type SceneMode = 'jobs' | 'workflow'
  const [sceneMode, setSceneMode] = useState<SceneMode>('jobs')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [jobNames, setJobNames] = useState<Map<string, string>>(new Map())
  // Stockage des canvas par job (ref mutable, pas besoin de re-render à chaque switch)
  const jobCanvasRef = useRef(new Map<string, { nodes: Node[]; edges: Edge[] }>())
  // Snapshot du canvas workflow (nécessaire pour afficher les tabs quand on est en job mode)
  const [wfSnapshot, setWfSnapshot] = useState<{ nodes: Node[]; edges: Edge[] } | null>(null)

  // Helpers de scène
  const isJobScene    = sceneMode === 'jobs'
  const activeJobName = activeJobId ? (jobNames.get(activeJobId) ?? activeJobId) : null

  // ── Navigation entre workflows du projet ─────────────────────────────────
  const navigate = useNavigate()

  // ── Menu contextuel des onglets workflow ─────────────────────────────────
  const [tabMenu, setTabMenu]             = useState<{ jobId: string; x: number; y: number } | null>(null)
  const [renamingJobId, setRenamingJobId] = useState<string | null>(null)
  const [jobScene2Menu, setJobScene2Menu] = useState<{ nodeId: string; x: number; y: number } | null>(null)

  // ── Undo / Redo ──────────────────────────────────────────────────────────
  // Modèle : push() AVANT chaque action destructive (delete, connect, drop).
  // Pas de debounce — évite que le useEffect poste la state POST-action avant
  // que Ctrl+Z soit pressé.
  const { push: pushHistory, undo: undoSnap, redo: redoSnap, canUndo, canRedo } = useUndoRedo()

  const handleUndo = useCallback(() => {
    const snap = undoSnap(nodes, edges)
    if (!snap) return
    setNodes(snap.nodes as Node<FlowNodeData>[])
    setEdges(snap.edges)
  }, [nodes, edges, undoSnap, setNodes, setEdges])

  const handleRedo = useCallback(() => {
    const snap = redoSnap(nodes, edges)
    if (!snap) return
    setNodes(snap.nodes as Node<FlowNodeData>[])
    setEdges(snap.edges)
  }, [nodes, edges, redoSnap, setNodes, setEdges])

  // ── Mode interaction + Minimap ────────────────────────────────────────────
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('pan')
  const [minimapVisible,  setMinimapVisible]  = useState(true)

  // ── Multi-sélection ───────────────────────────────────────────────────────
  const [multiSel, setMultiSel] = useState<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] })

  const onSelectionChange = useCallback(({ nodes: sns, edges: ses }: { nodes: Node[]; edges: Edge[] }) => {
    setMultiSel({ nodes: sns, edges: ses })
  }, [])

  /** Fix : supprimer un noeud job du canvas workflow retire aussi le job (jobNames + jobCanvasRef). */
  const cascadeDeleteJobs = useCallback((deletedNodes: Node[]) => {
    if (sceneMode !== 'workflow') return
    const del = deletedNodes.filter(n => (n.data as FlowNodeData)?.nodeType === 'job').map(n => ((n.data as any)?.jobRef as string) ?? n.id)
    if (del.length === 0) return
    const next = new Map(jobNames)
    for (const id of del) { next.delete(id); jobCanvasRef.current.delete(id) }
    setJobNames(next)
    if (activeJobId && !next.has(activeJobId)) setActiveJobId(next.size > 0 ? [...next.keys()][0] : null)
  }, [sceneMode, jobNames, activeJobId])
  const cascadeDeleteJobsRef = useRef(cascadeDeleteJobs)
  cascadeDeleteJobsRef.current = cascadeDeleteJobs

  /** React Flow onNodesDelete : pour un noeud job, propose scene-seule vs suppression complete (liste + disque). */
  const onNodesDelete = useCallback((deleted: Node[]) => {
    // Conteneur supprimé → détacher ses enfants (jamais de parentId orphelin,
    // les nœuds et leurs liens amont/aval sont préservés).
    const deletedContainers = new Set(deleted.filter(isContainerNode).map(n => n.id))
    if (deletedContainers.size > 0) {
      const inst = rfInstanceRef.current
      setNodes(nds => nds.map(n => {
        if (n.parentId && deletedContainers.has(n.parentId)) {
          const abs = inst?.getInternalNode(n.id)?.internals.positionAbsolute ?? n.position
          const { parentId: _p, extent: _e, ...rest } = n as Node<FlowNodeData> & { extent?: unknown }
          return { ...(rest as Node<FlowNodeData>), position: { x: abs.x, y: abs.y } }
        }
        return n
      }))
    }

    const jobNodes = deleted.filter(n => (n.data as FlowNodeData)?.nodeType === 'job')
    if (jobNodes.length === 0 || sceneMode !== 'workflow') return
    const label = jobNames.get(((jobNodes[0].data as any)?.jobRef as string) ?? jobNodes[0].id) ?? ''
    const alsoDelete = window.confirm(
      (jobNodes.length === 1
        ? `Job "${label}" retire de la scene.`
        : `${jobNodes.length} jobs retires de la scene.`) +
      `\n\nOK = supprimer aussi le job (retire de la liste Jobs + dossier disque)\n` +
      `Annuler = retirer de la scene seulement`
    )
    if (!alsoDelete) return
    const ids = jobNodes.map(n => ((n.data as any)?.jobRef as string) ?? n.id)
    const next = new Map(jobNames)
    for (const id of ids) {
      const name = jobNames.get(id) ?? id
      next.delete(id)
      jobCanvasRef.current.delete(id)
      if (projectId) api.jobs.delete(projectId, name).catch(() => {})
    }
    setJobNames(next)
    if (activeJobId && !next.has(activeJobId)) setActiveJobId(next.size > 0 ? [...next.keys()][0] : null)
  }, [sceneMode, jobNames, activeJobId, projectId, setNodes])

  // ── Conteneurs (Sequence Container & futurs types) ────────────────────────
  // Regroupe la sélection courante dans un nouveau Sequence Container.
  const groupSelectionIntoContainer = useCallback(() => {
    const inst = rfInstanceRef.current
    if (!inst) return
    const selSet = new Set(multiSel.nodes.map(n => n.id))
    const roots = multiSel.nodes.filter(n => !n.parentId || !selSet.has(n.parentId))
    if (roots.length === 0) return
    // Bounding box en coordonnées absolues
    const boxes = roots.map(n => {
      const int = inst.getInternalNode(n.id)
      const p = int?.internals.positionAbsolute ?? n.position
      return { x: p.x, y: p.y, w: int?.measured?.width ?? 80, h: int?.measured?.height ?? 80 }
    })
    const minX = Math.min(...boxes.map(b => b.x))
    const minY = Math.min(...boxes.map(b => b.y))
    const maxX = Math.max(...boxes.map(b => b.x + b.w))
    const maxY = Math.max(...boxes.map(b => b.y + b.h))
    const cx = minX - CONTAINER_PAD
    const cy = minY - CONTAINER_PAD - CONTAINER_HEADER_H
    const cw = Math.max(CONTAINER_DEFAULT_W, (maxX - minX) + CONTAINER_PAD * 2)
    const ch = Math.max(CONTAINER_DEFAULT_H, (maxY - minY) + CONTAINER_PAD * 2 + CONTAINER_HEADER_H)
    const cid = newNodeId('container')
    const container: Node<FlowNodeData> = {
      id: cid, type: 'container', position: { x: cx, y: cy },
      style: { width: cw, height: ch },
      data: { label: 'Sequence', nodeType: 'container', containerType: 'sequence', stepName: cid, enabled: true },
    }
    const selIds = new Set(roots.map(n => n.id))
    pushHistory(nodes, edges)
    setNodes(nds => {
      const reparented = nds.map(n => {
        if (!selIds.has(n.id)) return n
        const p = inst.getInternalNode(n.id)?.internals.positionAbsolute ?? n.position
        return { ...n, parentId: cid, extent: 'parent' as const, position: { x: p.x - cx, y: p.y - cy } }
      })
      return reorderParentsFirst([container, ...reparented])
    })
    setMultiSel({ nodes: [], edges: [] })
  }, [multiSel, nodes, edges, pushHistory, setNodes])

  // Drag terminé : (dé)rattache un nœud OU un conteneur au conteneur qu'il survole
  // (imbrication supportée ; attachNodeToContainer refuse les cycles).
  const onNodeDragStop = useCallback((_: unknown, dragged: Node) => {
    const inst = rfInstanceRef.current
    if (!inst) return
    const cur = inst.getNodes() as Node<FlowNodeData>[]
    const curEdges = inst.getEdges()
    const draggedIsContainer = isContainerNode(dragged)
    // conteneurs survolés, hors soi-même et hors ses propres descendants
    const target = inst.getIntersectingNodes(dragged)
      .filter(n => isContainerNode(n) && n.id !== dragged.id)
      .find(t => !draggedIsContainer || !isDescendant(cur as never, t.id, dragged.id))
    const currentParent = dragged.parentId
    if (target && target.id !== currentParent) {
      pushHistory(nodes, edges)
      const res = attachNodeToContainer(cur as never, curEdges, dragged.id, target.id)
      setNodes(res.nodes as never); setEdges(res.edges)
    } else if (!target && currentParent) {
      pushHistory(nodes, edges)
      const res = detachNode(cur as never, curEdges, dragged.id)
      setNodes(res.nodes as never); setEdges(res.edges)
    }
  }, [nodes, edges, pushHistory, setNodes, setEdges])

  // Rattacher / détacher un nœud à un conteneur (depuis le menu contextuel « … »)
  const attachToContainer = useCallback((nodeId: string, containerId: string) => {
    pushHistory(nodes, edges)
    const res = attachNodeToContainer(nodes as never, edges, nodeId, containerId)
    setNodes(res.nodes as never); setEdges(res.edges)
  }, [nodes, edges, pushHistory, setNodes, setEdges])

  const detachFromContainer = useCallback((nodeId: string) => {
    pushHistory(nodes, edges)
    const res = detachNode(nodes as never, edges, nodeId)
    setNodes(res.nodes as never); setEdges(res.edges)
  }, [nodes, edges, pushHistory, setNodes, setEdges])

  const deleteSelection = useCallback(() => {
    if (multiSel.nodes.length === 0 && multiSel.edges.length === 0) return
    pushHistory(nodes, edges)   // snapshot avant suppression
    rfInstanceRef.current?.deleteElements({
      nodes: multiSel.nodes.map(n => ({ id: n.id })),
      edges: multiSel.edges.map(e => ({ id: e.id })),
    })
    setMultiSel({ nodes: [], edges: [] })
    setSelectedNode(null)
  }, [multiSel, nodes, edges, pushHistory])

  // ── Charger workflow ──────────────────────────────────────────────────────

  const wfQuery = useQuery({
    queryKey: ['workflow', workflowId, projectId],
    queryFn:  () => api.workflows.get(workflowId!, projectId),
    enabled:  Boolean(workflowId && projectId),
  })

  useEffect(() => {
    if (!wfQuery.data) return
    // Ne (ré)initialiser QUE au 1er chargement d'un workflow. Un refetch (auto-save
    // qui invalide la requête) ne doit PAS réinitialiser la scène ni écraser les
    // éditions → évite les sauts involontaires Workflow ↔ Job config.
    if (initializedWfRef.current === (workflowId ?? '')) return
    initializedWfRef.current = workflowId ?? ''
    canAutoSave.current = false
    setLoadIssues([])
    let cancelled = false

    const layout = wfQuery.data.layout as {
      nodes?: Node<FlowNodeData>[]
      edges?: Edge[]
      job_canvases?: Record<string, { nodes: Node[]; edges: Edge[] }>
      job_names?:    Record<string, string>
    } | undefined

    const savedJobNames = layout?.job_names ?? {}
    // Sanitisation : un layout corrompu (fichier édité à la main, session
    // interrompue, données invalides) ne doit jamais produire de page blanche
    const { nodes: wfNodes, edges: wfEdges } = sanitizeCanvas(layout?.nodes, layout?.edges)
    const jobCanvases: Record<string, { nodes: Node[]; edges: Edge[] }> = {}
    Object.entries(layout?.job_canvases ?? {}).forEach(([id, c]) => {
      jobCanvases[id] = sanitizeCanvas((c as { nodes?: unknown })?.nodes, (c as { edges?: unknown })?.edges)
    })

    // Construire la map de noms de jobs
    const namesMap = new Map<string, string>()
    Object.entries(jobCanvases).forEach(([id, canvas]) => {
      jobCanvasRef.current.set(id, canvas)
      namesMap.set(id, savedJobNames[id] ?? id)
    })
    setJobNames(namesMap)
    setWfSnapshot({ nodes: wfNodes as Node[], edges: wfEdges })

    if (namesMap.size === 0) {
      // Aucun job canvas sauvegardé — Scene 2 (Workflow configuration).
      // Si le layout est vide mais que workflow.yaml a des steps (projet créé
      // au CLI / à la main), reconstruire le canvas depuis le YAML.
      let initNodes = wfNodes as Node<FlowNodeData>[]
      let initEdges = wfEdges
      let parsed: ReturnType<typeof parseWorkflowYAML> = null
      if (initNodes.length === 0 && wfQuery.data.yaml_content) {
        parsed = parseWorkflowYAML(wfQuery.data.yaml_content)
        if (parsed && parsed.workflow.steps.length > 0) {
          try {
            const flow = workflowToFlow(parsed)
            initNodes = flow.nodes
            initEdges = flow.edges
          } catch { /* YAML invalide — canvas vide */ }
        }
      }
      setNodes(initNodes)
      setEdges(initEdges)
      setSceneMode('workflow')
      setActiveJobId(null)
      if (initNodes.length > 0) fitViewSoon(150)

      // Charger les 4 YAML de chaque job référencé (jobs/<nom>/ sur disk)
      // → remplit l'onglet « Jobs configuration » et bascule sur le 1er job
      const jobSteps = (parsed?.workflow.steps ?? []).filter(s => s.type === 'job' && s.job)
      const baseName = (p: string) =>
        p.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? p

      // ── Diagnostics manifests : nom de fichier + ligne exacte de l'erreur ──
      const issues: string[] = []
      const checkYaml = (label: string, text: string): boolean => {
        try { YAML.load(text); return true } catch (e) {
          const mark = (e as { mark?: { line?: number; column?: number } }).mark
          const pos = mark?.line != null
            ? ` — ligne ${mark.line + 1}${mark.column != null ? `, colonne ${mark.column + 1}` : ''}`
            : ''
          issues.push(`${label}${pos} : ${(((e as Error).message) ?? 'YAML invalide').split('\n')[0]}`)
          return false
        }
      }
      // workflow.yaml lui-même illisible → fichier + ligne
      if (wfQuery.data.yaml_content && !parsed) {
        checkYaml(`workflows/${baseName(wfQuery.data.path ?? 'workflow.yaml')}`, wfQuery.data.yaml_content)
        setLoadIssues([...issues])
      }

      if (jobSteps.length > 0 && projectId) {
        Promise.all(jobSteps.map(async step => {
          const jobName = baseName(step.job as string)
          try {
            const files = await api.jobs.files(projectId, jobName)
            // Valider chaque fichier individuellement → erreur localisée
            const reqOk = (['sources', 'destinations', 'pipeline'] as const)
              .map(sec => files[sec]?.trim()
                ? checkYaml(`jobs/${jobName}/${sec}.yaml`, files[sec])
                : (issues.push(`jobs/${jobName}/${sec}.yaml : fichier vide ou introuvable`), false))
              .every(Boolean)
            const tfOk = !files.transformations?.trim()
              || checkYaml(`jobs/${jobName}/transformations.yaml`, files.transformations)
            if (!reqOk || !tfOk) return null
            const model = sectionYamlsToJobModel({
              sources: files.sources, transformations: files.transformations,
              destinations: files.destinations, pipeline: files.pipeline,
            }, jobName)
            if (!model) {
              issues.push(`jobs/${jobName}/ : structure incohérente (sections sources/destinations/pipeline)`)
              return null
            }
            const canvas = jobModelToFlow(model)
            return { jobName, canvas }
          } catch (e) {
            issues.push(`jobs/${jobName}/ : ${(e as Error).message ?? 'chargement impossible'}`)
            return null
          }
        })).then(results => {
          if (cancelled) return
          if (issues.length > 0) setLoadIssues([...issues])
          const loaded = results.filter((r): r is NonNullable<typeof r> => r != null)
          if (loaded.length === 0) return          // rien sur disk — canvas workflow seul
          const names = new Map<string, string>()
          loaded.forEach(({ jobName, canvas }) => {
            jobCanvasRef.current.set(jobName, canvas)
            names.set(jobName, jobName)
          })
          // jobRef sur les nœuds workflow → le double-clic ouvre le bon canvas
          const patchedWfNodes = initNodes.map(n => {
            const d = n.data as FlowNodeData
            if (d.nodeType !== 'job' || !d.jobPath) return n
            const ref = baseName(d.jobPath as string)
            return names.has(ref) ? { ...n, data: { ...d, jobRef: ref } } : n
          })
          setJobNames(names)
          setWfSnapshot({ nodes: patchedWfNodes as Node[], edges: initEdges })
          // Basculer en Scene 1 (Jobs configuration) — deep-link jobId respecté
          const firstId = resolveJobKey(names, sp.get('jobId')) ?? names.keys().next().value!
          const c = jobCanvasRef.current.get(firstId) ?? { nodes: [], edges: [] }
          setNodes(c.nodes as Node<FlowNodeData>[])
          setEdges(c.edges)
          setSceneMode('jobs')
          setActiveJobId(firstId)
          fitViewSoon(150)
        })
      }
    } else {
      // Démarrer en Scene 1 (Jobs configuration) — deep-link ou premier job
      const firstJobId = resolveJobKey(namesMap, sp.get('jobId'))
        ?? namesMap.keys().next().value!
      const savedCanvas = jobCanvasRef.current.get(firstJobId) ?? { nodes: [], edges: [] }
      setNodes(savedCanvas.nodes as Node<FlowNodeData>[])
      setEdges(savedCanvas.edges)
      setSceneMode('jobs')
      setActiveJobId(firstJobId)
      if (savedCanvas.nodes.length > 0) fitViewSoon(150)
    }

    // Autorise l'auto-save 300ms après le chargement (évite la boucle initiale)
    setTimeout(() => { canAutoSave.current = true }, 300)
    return () => { cancelled = true }
  }, [wfQuery.data])

  // ── Fermer le panel si le nœud sélectionné est supprimé ──────────────────

  useEffect(() => {
    if (selectedNode && !nodes.find(n => n.id === selectedNode.id)) {
      setSelectedNode(null)
      setRenameNodeId(null)
    }
  }, [nodes, selectedNode])

  // ── Validation en temps réel ──────────────────────────────────────────────

  useEffect(() => {
    // Les conteneurs sont visuels : exclus du DAG de validation.
    const dagCandidates = nodes.filter(n => !isContainerNode(n))
    if (dagCandidates.length === 0) { setValidationErrors([]); return }
    const dagNodes = edgesToDAGNodes(
      dagCandidates.map(n => n.id),
      edges.filter(e => !isProxyEdge(e)).map(e => ({ source: e.source, target: e.target })),
    )
    setValidationErrors(validateDAG(dagNodes).errors)
  }, [nodes, edges])

  // ── Navigation : Workflow ↔ Job canvases ─────────────────────────────────

  /** Bascule vers Scene 2 (Workflow configuration) */
  const switchToWorkflowScene = useCallback(() => {
    if (sceneMode === 'workflow') return
    if (activeJobId) jobCanvasRef.current.set(activeJobId, { nodes: [...nodes], edges: [...edges] })
    const snap = wfSnapshot ?? { nodes: [], edges: [] }
    setNodes(snap.nodes as Node<FlowNodeData>[])
    setEdges(snap.edges)
    setSceneMode('workflow')
    setSp(prev => { const n = new URLSearchParams(prev); n.delete('jobId'); return n }, { replace: true })
    if (snap.nodes.length > 0) fitViewSoon()
  }, [sceneMode, activeJobId, nodes, edges, wfSnapshot, setSp, fitViewSoon])

  /** Bascule vers Scene 1 (Jobs configuration) sur le job donné */
  const switchToJobScene = useCallback((jobId: string) => {
    if (sceneMode === 'jobs' && activeJobId === jobId) return
    if (sceneMode === 'workflow') {
      setWfSnapshot({ nodes: [...nodes], edges: [...edges] })
    } else if (activeJobId) {
      jobCanvasRef.current.set(activeJobId, { nodes: [...nodes], edges: [...edges] })
    }
    const saved = jobCanvasRef.current.get(jobId) ?? { nodes: [], edges: [] }
    setNodes(saved.nodes as Node<FlowNodeData>[])
    setEdges(saved.edges)
    setSceneMode('jobs')
    setActiveJobId(jobId)
    setSp(prev => { const n = new URLSearchParams(prev); n.set('jobId', jobId); return n }, { replace: true })
    if (saved.nodes.length > 0) fitViewSoon()
  }, [sceneMode, activeJobId, nodes, edges, setSp, fitViewSoon])

  /** Crée un nouveau job vide et bascule en Scene 1 */
  const addJob = useCallback(() => {
    const newId   = `job_${Date.now()}`
    const newName = `job${jobNames.size + 1}`
    if (sceneMode === 'jobs' && activeJobId) {
      jobCanvasRef.current.set(activeJobId, { nodes: [...nodes], edges: [...edges] })
    }
    jobCanvasRef.current.set(newId, { nodes: [], edges: [] })
    setJobNames(prev => { const next = new Map(prev); next.set(newId, newName); return next })
    setNodes([])
    setEdges([])
    setSceneMode('jobs')
    setActiveJobId(newId)
    setSp(prev => { const n = new URLSearchParams(prev); n.set('jobId', newId); return n }, { replace: true })
  }, [sceneMode, activeJobId, nodes, edges, jobNames, setSp])

  /** Renomme un job (inline depuis l'onglet) */
  const renameJob = useCallback((jobId: string, newName: string) => {
    const trimmed = newName.trim()
    setRenamingJobId(null)
    if (!trimmed) return
    setJobNames(prev => { const next = new Map(prev); next.set(jobId, trimmed); return next })
    // Mettre à jour le label du nœud correspondant dans le canvas Scene 2
    setWfSnapshot(prev => prev ? ({
      ...prev,
      nodes: prev.nodes.map(n => n.id === jobId ? { ...n, data: { ...n.data, label: trimmed } } : n),
    }) : prev)
  }, [])

  /** Supprime un job (bloqué si le job est sur le canvas Scene 2) */
  const deleteJob = useCallback((jobId: string) => {
    setTabMenu(null)
    const wfNodes = sceneMode === 'workflow' ? nodes : ((wfSnapshot?.nodes ?? []) as Node<FlowNodeData>[])
    if (wfNodes.some(n => n.id === jobId || (n.data as any)?.jobRef === jobId)) {
      alert(`Impossible de supprimer "${jobNames.get(jobId) ?? jobId}" : retirez-le d'abord du canvas "Workflow configuration".`)
      return
    }
    const delName = jobNames.get(jobId) ?? jobId
    const alsoDisk = window.confirm(
      `Supprimer le job "${delName}".\n\n` +
      `OK = supprimer aussi le dossier sur le disque (jobs/${delName}/)\n` +
      `Annuler = retirer de Hydra Studio seulement`
    )
    const newNames = new Map(jobNames)
    newNames.delete(jobId)
    jobCanvasRef.current.delete(jobId)
    setJobNames(newNames)
    if (activeJobId === jobId) {
      if (newNames.size > 0) {
        const nextId = [...newNames.keys()][0]
        const saved  = jobCanvasRef.current.get(nextId) ?? { nodes: [], edges: [] }
        setNodes(saved.nodes as Node<FlowNodeData>[])
        setEdges(saved.edges)
        setActiveJobId(nextId)
        setSp(prev => { const n = new URLSearchParams(prev); n.set('jobId', nextId); return n }, { replace: true })
        if (saved.nodes.length > 0) fitViewSoon()
      } else {
        setActiveJobId(null)
        setNodes([])
        setEdges([])
      }
    }
    if (alsoDisk && projectId) api.jobs.delete(projectId, delName).catch(() => {})
  }, [sceneMode, nodes, wfSnapshot, jobNames, activeJobId, setSp, projectId])

  /** Archive un job : dossier renomme en <nom>.backup (bloque si sur le canvas). */
  const archiveJob = useCallback((jobId: string) => {
    setTabMenu(null)
    const wfNodes = sceneMode === 'workflow' ? nodes : ((wfSnapshot?.nodes ?? []) as Node<FlowNodeData>[])
    if (wfNodes.some(n => n.id === jobId || (n.data as any)?.jobRef === jobId)) {
      alert(`Impossible d'archiver "${jobNames.get(jobId) ?? jobId}" : retirez-le d'abord du canvas "Workflow configuration".`)
      return
    }
    const name = jobNames.get(jobId) ?? jobId
    const newNames = new Map(jobNames)
    newNames.delete(jobId)
    jobCanvasRef.current.delete(jobId)
    setJobNames(newNames)
    if (activeJobId === jobId) {
      if (newNames.size > 0) {
        const nextId = [...newNames.keys()][0]
        const saved  = jobCanvasRef.current.get(nextId) ?? { nodes: [], edges: [] }
        setNodes(saved.nodes as Node<FlowNodeData>[])
        setEdges(saved.edges)
        setActiveJobId(nextId)
      } else {
        setActiveJobId(null); setNodes([]); setEdges([])
      }
    }
    if (projectId) api.jobs.archive(projectId, name).then(r => { if (r?.message) console.info(r.message) }).catch(() => {})
  }, [sceneMode, nodes, wfSnapshot, jobNames, activeJobId, projectId])

  /** Ouvre le menu contextuel (Renommer/Archiver/Supprimer) depuis la liste Jobs de la palette. */
  const onJobContextMenu = useCallback((e: React.MouseEvent, jobId: string) => {
    e.preventDefault()
    setTabMenu({ jobId, x: e.clientX, y: e.clientY + 72 })
  }, [])

  /** Duplique un nœud job sur le canvas Scene 2 (avec confirmation) */
  const duplicateJobInScene2 = useCallback((nodeId: string) => {
    const sourceNode = nodes.find(n => n.id === nodeId)
    if (!sourceNode) return
    const origJobId = (sourceNode.data as any)?.jobRef ?? nodeId
    const jobName   = jobNames.get(origJobId) ?? origJobId
    if (!window.confirm(`Dupliquer "${jobName}" sur le canvas ?\nLes deux nœuds pointeront vers le même pipeline.`)) return
    const dupId   = `${nodeId}_dup_${Date.now()}`
    const dupNode = {
      ...sourceNode,
      id:       dupId,
      position: { x: sourceNode.position.x + 40, y: sourceNode.position.y + 40 },
      selected: false,
      data:     { ...(sourceNode.data as FlowNodeData), jobRef: origJobId },
    }
    pushHistory(nodes, edges)
    setNodes(nds => [...nds, dupNode as Node<FlowNodeData>])
    setJobScene2Menu(null)
  }, [nodes, edges, jobNames, pushHistory])

  // ── Écouter custom events des HydraNodes ─────────────────────────────────

  useEffect(() => {
    const onOpenPanel = (e: Event) => {
      const { nodeId } = (e as CustomEvent).detail
      const node = rfInstance?.getNodes().find(n => n.id === nodeId)
      if (node) setDialogNode(node as Node<FlowNodeData>)
    }
    const onRunStep = (e: Event) => {
      const { nodeId } = (e as CustomEvent).detail
      const currentNodes = (rfInstance?.getNodes() ?? []) as Node<FlowNodeData>[]
      const node = currentNodes.find(n => n.id === nodeId)
      if (!node) return
      const nt = (node.data as FlowNodeData).nodeType ?? ''
      // Nœud action shell → exécution directe via endpoint action
      if (nt === 'action_powershell' || nt === 'action_bash' || nt === 'action_ssh' || nt === 'action_webhook' || nt === 'action_python') {
        runActionRef.current(node as Node<FlowNodeData>)
        return
      }
      // En mode Job Builder, pas de step partiel — exécuter le job complet inline
      if (sceneMode === 'jobs') { stepRunRef.current(node.id); return }
      if (!wfQuery.data?.path) return
      runStepMut.mutate({ workflow_path: wfQuery.data.path, step: (node.data as FlowNodeData).stepName })
    }
    const onNodeMenu = (e: Event) => {
      const { nodeId, x, y } = (e as CustomEvent).detail
      const node = rfInstance?.getNodes().find(n => n.id === nodeId)
      if (node) { setSelectedNode(node as Node<FlowNodeData>); setContextMenu({ nodeId, x, y }) }
    }
    document.addEventListener('hydra:open-panel', onOpenPanel)
    document.addEventListener('hydra:run-step',   onRunStep)
    document.addEventListener('hydra:node-menu',  onNodeMenu)
    return () => {
      document.removeEventListener('hydra:open-panel', onOpenPanel)
      document.removeEventListener('hydra:run-step',   onRunStep)
      document.removeEventListener('hydra:node-menu',  onNodeMenu)
    }
  }, [rfInstance, wfQuery.data, sceneMode])

  // ── Connexions ────────────────────────────────────────────────────────────

  const onConnect = useCallback((params: Connection) => {
    pushHistory(nodes, edges)   // snapshot avant ajout de lien
    setEdges(eds => addEdge({ ...params, type: 'smoothstep', animated: false, markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 } }, eds))
  }, [nodes, edges, pushHistory])

  // Double-clic sur une contrainte (arête) -> suppression immediate
  const onEdgeDoubleClick = useCallback((_evt: React.MouseEvent, edge: Edge) => {
    pushHistory(nodes, edges)   // snapshot avant suppression
    setEdges(eds => eds.filter(e => e.id !== edge.id))
  }, [nodes, edges, pushHistory, setEdges])

  // Aretes affichees : injecte une fleche de terminaison si absente
  const displayEdges = useMemo(
    () => edges.map(e => (e.markerEnd ? e : { ...e, markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 } })),
    [edges],
  )

  // ── Drag & drop depuis palette ────────────────────────────────────────────

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onJobDragStart = useCallback((e: React.DragEvent, jobId: string) => {
    e.dataTransfer.setData('application/hydra-job-ref', jobId)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()

    // Job-ref drag depuis la palette Scene 2
    const jobRefId = e.dataTransfer.getData('application/hydra-job-ref')
    if (jobRefId && rfInstance) {
      const alreadyOnCanvas = nodes.some(n => n.id === jobRefId || (n.data as any)?.jobRef === jobRefId)
      if (alreadyOnCanvas) {
        alert(`Le job "${jobNames.get(jobRefId) ?? jobRefId}" est déjà sur le canvas.\nUtilisez le clic droit pour dupliquer.`)
        return
      }
      const jobName = jobNames.get(jobRefId) ?? jobRefId
      const position = rfInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY })
      const newNode: Node<FlowNodeData> = {
        id: jobRefId, type: 'hydraNode', position,
        data: { label: jobName, nodeType: 'job', stepName: jobRefId, jobRef: jobRefId, enabled: true, onFailure: 'fail' } as FlowNodeData,
      }
      pushHistory(nodes, edges)
      setNodes(nds => [...nds, newNode])
      setSelectedNode(newNode)
      return
    }

    // Mode replace : l'utilisateur a sélectionné un nouveau type depuis la palette
    if (replaceNodeId) {
      const newType = e.dataTransfer.getData('application/hydra-node')
      if (newType) {
        setNodes(nds => nds.map(n => {
          if (n.id !== replaceNodeId) return n
          const def      = getNode(newType)
          const isAction = def?.category === 'action'
          return {
            ...n,
            type: 'hydraNode',
            data: {
              ...n.data,
              label:    def?.label ?? newType,
              nodeType: newType,
              jobPath:  isAction ? undefined : '',
              action:   isAction ? def?.type.replace('action_', '') : undefined,
            },
          }
        }))
        setSelectedNode(null)
      }
      setReplaceNodeId(null)
      return
    }

    const nodeType = e.dataTransfer.getData('application/hydra-node')
    if (!nodeType || !rfInstance) return

    const position = rfInstance.screenToFlowPosition({
      x: e.clientX,
      y: e.clientY,
    })
    // Conteneur : nœud de regroupement vide (glissé depuis la section Containers)
    if (nodeType === CONTAINER_NODE_TYPE || nodeType.startsWith(CONTAINER_NODE_TYPE + ':')) {
      const sub = nodeType.includes(':') ? nodeType.split(':')[1] : 'sequence'
      const isErr = sub === 'errorscope'
      const isRetry = sub === 'retryscope'
      const cLabel = isErr ? 'Error Scope' : isRetry ? 'Retry Scope' : 'Sequence'
      const cid = newNodeId('container')
      const container: Node<FlowNodeData> = {
        id: cid, type: 'container', position,
        style: { width: CONTAINER_DEFAULT_W, height: CONTAINER_DEFAULT_H },
        data: {
          label: cLabel,
          nodeType: 'container',
          containerType: sub as FlowNodeData['containerType'],
          stepName: cid, enabled: true,
          ...(isErr ? { onFailure: 'skip' as const } : {}),
          ...(isRetry ? { retry: { max: 3, delay: 5 } } : {}),
        },
      }
      pushHistory(nodes, edges)
      setNodes(nds => [container, ...nds])
      setSelectedNode(container)
      return
    }
    const newNode = makeFlowNode(nodeType, position)
    pushHistory(nodes, edges)   // snapshot avant ajout du nœud
    setNodes(nds => [...nds, newNode])

    // Ouvrir immédiatement le panel propriétés pour le nouveau nœud
    setSelectedNode(newNode)
  }, [rfInstance, replaceNodeId, nodes, edges, pushHistory])

  const onDragStart = useCallback((e: React.DragEvent, nodeType: string) => {
    e.dataTransfer.setData('application/hydra-node', nodeType)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  // ── Sélection / double-clic ───────────────────────────────────────────────

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node as Node<FlowNodeData>)
    setContextMenu(null)
  }, [])

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (isContainerNode(node)) return   // un conteneur n'a pas de config (socle)
    if ((node.data as FlowNodeData).nodeType === 'job') {
      const targetJobId = (node.data as any).jobRef ?? node.id
      switchToJobScene(targetJobId)
      return
    }
    setDialogNode(node as Node<FlowNodeData>)
  }, [switchToJobScene])

  // ── Menu contextuel ───────────────────────────────────────────────────────

  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault()
    if (sceneMode === 'workflow' && (node.data as FlowNodeData).nodeType === 'job') {
      setJobScene2Menu({ nodeId: node.id, x: e.clientX, y: e.clientY })
      setSelectedNode(node as Node<FlowNodeData>)
      return
    }
    setContextMenu({ nodeId: node.id, x: e.clientX, y: e.clientY })
    setSelectedNode(node as Node<FlowNodeData>)
  }, [sceneMode])

  // ── Modifications depuis le panel ─────────────────────────────────────────

  const onNodeDataChange = useCallback((id: string, patch: Partial<FlowNodeData>) => {
    setNodes(nds => nds.map(n => n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
    setSelectedNode(prev => prev?.id === id ? { ...prev, data: { ...prev.data, ...patch } } : prev)
  }, [])

  // ── Raccourcis clavier canvas ─────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!selectedNode) return
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        setRenameNodeId(selectedNode.id)
      }
      if (e.key === 'd' || e.key === 'D') {
        e.preventDefault()
        const enabled = (selectedNode.data as FlowNodeData).enabled !== false
        onNodeDataChange(selectedNode.id, { enabled: !enabled })
      }
      if (e.key === 'p' || e.key === 'P') {
        e.preventDefault()
        setReplaceNodeId(selectedNode.id)
      }
      if (e.key === 'i' || e.key === 'I') {
        e.preventDefault()
        const pinned = Boolean((selectedNode.data as FlowNodeData).pinned)
        onNodeDataChange(selectedNode.id, { pinned: !pinned })
        setNodes(nds => nds.map(n =>
          n.id === selectedNode.id ? { ...n, draggable: pinned } : n
        ))
      }
      if (e.key === ' ') {
        e.preventDefault()
        if (isJobScene) {
          runJobRef.current()
        } else if (wfQuery.data?.path) {
          runStepMut.mutate({
            workflow_path: wfQuery.data.path,
            step: (selectedNode.data as FlowNodeData).stepName,
          })
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedNode, wfQuery.data])

  // ── Mutations API ─────────────────────────────────────────────────────────

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!workflowId || !projectId) throw new Error('workflowId / projectId manquants')
      const currentJobCanvases = Object.fromEntries(jobCanvasRef.current)
      const allJobCanvases = (sceneMode === 'jobs' && activeJobId)
        ? { ...currentJobCanvases, [activeJobId]: { nodes, edges } }
        : currentJobCanvases
      const wfNodes = sceneMode === 'workflow' ? nodes : ((wfSnapshot?.nodes ?? []) as Node<FlowNodeData>[])
      const wfEdges = sceneMode === 'workflow' ? edges : (wfSnapshot?.edges ?? [])
      const jobNamesObj = Object.fromEntries(jobNames)
      const wf = flowToWorkflow(withJobPaths(wfNodes, jobNames), wfEdges, {
        name:        wfQuery.data?.name ?? 'workflow',
        triggerType: (wfQuery.data?.trigger_type ?? 'manual') as 'manual' | 'schedule' | 'webhook',
        cron:        wfQuery.data?.cron,
      })
      await api.workflows.update(workflowId, projectId, {
        layout: {
          nodes:        wfNodes,
          edges:        wfEdges,
          job_canvases: allJobCanvases,
          job_names:    jobNamesObj,
        },
        yaml_content: workflowToYAMLString(wf),
        // Symétrie CLI ↔ Studio : chaque job canvas devient un vrai dossier jobs/<nom>/
        jobs: buildJobsPayload(allJobCanvases as Record<string, { nodes: Node[]; edges: Edge[] }>, jobNames),
      })
    },
    onMutate:  () => setSaveStatus('saving'),
    onSuccess: () => {
      setSaveStatus('saved')
      qc.invalidateQueries({ queryKey: ['workflow', workflowId] })
      setTimeout(() => setSaveStatus('idle'), 2000)
    },
    onError: () => setSaveStatus('error'),
  })

  // ── Auto-save : délai configurable dans Settings ─────────────────────────
  useEffect(() => {
    if (!canAutoSave.current) return
    if (!workflowId || !projectId) return
    if (nodes.length === 0 && edges.length === 0) return
    const { autosave_enabled, autosave_delay } = loadSettings()
    if (!autosave_enabled) return
    const timer = setTimeout(() => { saveMut.mutate() }, autosave_delay)
    return () => clearTimeout(timer)
  }, [nodes, edges])

  // ── Indicateur de progression : colore les nœuds selon l'état du run ──────
  // blanc (initial) → pulsation ambre (running) → vert (success) / rouge (failed)
  const applyRunStatus = useCallback((run: Run | null, running: boolean) => {
    setNodes(nds => nds.map(n => {
      const d = n.data as FlowNodeData
      if (running) return { ...n, data: { ...d, runStatus: 'running' } }
      if (!run) return { ...n, data: { ...d, runStatus: undefined } }
      const st = (run.steps ?? []).find(s => s.step_name === d.stepName)
      if (st) {
        return { ...n, data: { ...d, runStatus: st.skipped ? undefined : st.success ? 'success' : 'failed' } }
      }
      // Run inline (job) : un seul step global → appliquer à tous les nœuds
      if ((run.steps ?? []).length <= 1) {
        return { ...n, data: { ...d, runStatus: run.status === 'success' ? 'success' : run.status === 'failed' ? 'failed' : undefined } }
      }
      return { ...n, data: { ...d, runStatus: undefined } }
    }))
  }, [setNodes])

  // ── Polling : rafraîchit lastRun toutes les 1.5s jusqu'à statut terminal ──
  const pollRun = (runId: string) => {
    const tick = async () => {
      try {
        const run = await api.runs.get(runId)
        setLastRun(run)
        if (run.status === 'pending' || run.status === 'running') {
          applyRunStatus(null, true)
          setTimeout(tick, 1500)
        } else {
          applyRunStatus(run, false)
        }
      } catch { /* ignore */ }
    }
    setTimeout(tick, 800)
  }

  // ── Lignes du volet logs (dérivées du dernier run) ─────────────────────────
  const logLines = useMemo(() => {
    if (!lastRun) return []
    const L: string[] = []
    L.push(`Run ${lastRun.run_id} — ${lastRun.workflow_name} [${lastRun.status.toUpperCase()}]`)
    if (lastRun.duration != null) L.push(`Durée totale : ${lastRun.duration.toFixed(2)}s`)
    if (lastRun.error) L.push(`ERROR ${lastRun.error}`)
    for (const s of lastRun.steps ?? []) {
      L.push(`— step ${s.step_name} : ${s.skipped ? 'SKIP' : s.success ? '✓ success' : '✗ FAILED'}${s.duration != null ? ` (${Number(s.duration).toFixed(2)}s)` : ''}`)
      if (s.rows_in != null || s.rows_out != null) L.push(`    rows_in=${s.rows_in ?? '—'}  rows_out=${s.rows_out ?? '—'}`)
      if (s.error) L.push(`    ERROR ${s.error}`)
      for (const line of s.logs ?? []) L.push(`    ${line}`)
    }
    if (lastRun.status === 'pending' || lastRun.status === 'running') L.push('… exécution en cours')
    return L
  }, [lastRun])

  const runMut = useMutation({
    mutationFn: async () => {
      if (!workflowId || !projectId) throw new Error('Workflow non initialisé')

      // Mode "action isolée" (powershell/bash/…) : UNIQUEMENT sur un canvas SANS job.
      // Dès qu'un nœud job est présent (= vrai workflow), Run lance le WORKFLOW complet
      // et non l'action seule (sinon l'action court-circuite l'exécution du workflow).
      const hasJobNode = nodes.some(n => (n.data as FlowNodeData).nodeType === 'job')
      const actionNode = hasJobNode ? undefined : (
        (selectedNode && (selectedNode.data as FlowNodeData).nodeType?.startsWith('action_'))
          ? selectedNode
          : nodes.find(n => (n.data as FlowNodeData).nodeType?.startsWith('action_'))
      )
      console.debug('[runMut] isJobScene=', isJobScene, 'actionNode=', actionNode?.id,
        'nodeType=', (actionNode?.data as any)?.nodeType,
        'params=', (actionNode?.data as any)?.params,
        'nodes=', nodes.map(n => (n.data as any)?.nodeType))
      if (!isJobScene && actionNode) {
        const data = actionNode.data as FlowNodeData
        const nodeType = data.nodeType ?? ''
        if (nodeType === 'action_powershell' || nodeType === 'action_bash' || nodeType === 'action_ssh' || nodeType === 'action_webhook' || nodeType === 'action_python') {
          const p = (data.params as Record<string, string>) ?? {}
          const command = nodeType === 'action_webhook' ? (p.url ?? '')
                        : nodeType === 'action_python'  ? (p.script ?? p.file_path ?? '')
                        : (p.command ?? '')
          if (!command.trim()) throw new Error(
            nodeType === 'action_webhook' ? 'Configurez d\'abord l\'URL dans le nœud (double-clic).'
            : nodeType === 'action_python' ? 'Configurez d\'abord le script Python dans le nœud (double-clic).'
            : 'Configurez d\'abord la commande dans le nœud (double-clic).'
          )
          return api.runs.startAction({
            node_type:   nodeType,
            command,
            working_dir: p.working_dir ?? undefined,
            timeout:     p.timeout ? Number(p.timeout) : 60,
            job_name:    wfQuery.data?.name ?? nodeType,
            params:      (nodeType === 'action_ssh' || nodeType === 'action_webhook') ? p : undefined,
          })
        }
      }

      if (sceneMode === 'jobs' && activeJobId) {
        const jobName    = activeJobName ?? wfQuery.data?.name ?? 'job'
        const hdrContent = flowToHdr(nodes, edges, jobName)
        // Résolution des chemins relatifs : priorité au dossier réel du job
        // (project/jobs/<nom>/ — même base que le CLI), sinon dossier importé.
        const projectRoot  = wfQuery.data?.path?.replace(/[\\/]workflows[\\/][^\\/]+$/, '')
        const jobDirOnDisk = (projectRoot && projectRoot !== wfQuery.data?.path && activeJobName)
          ? `${projectRoot}/jobs/${slugify(activeJobName)}`
          : undefined
        const workDir    = importedJobPath
          ?? jobDirOnDisk
          ?? (wfQuery.data?.path ? wfQuery.data.path.replace(/[\/][^\/]+$/, '') : undefined)
        return api.runs.startInline({ hdr_content: hdrContent, job_name: jobName, work_dir: workDir })
      }

      // Mode Workflow Orchestrateur : auto-save → disk → run
      if (!wfQuery.data?.path) throw new Error('Workflow non initialisé')
      const wf   = flowToWorkflow(withJobPaths(nodes, jobNames), edges, {
        name:        wfQuery.data?.name ?? 'workflow',
        triggerType: (wfQuery.data?.trigger_type ?? 'manual') as 'manual' | 'schedule' | 'webhook',
        cron:        wfQuery.data?.cron,
      })
      const yaml = workflowToYAMLString(wf)
      const jobCanvases = Object.fromEntries(jobCanvasRef.current)
      await api.workflows.update(workflowId, projectId, {
        layout:       { nodes, edges, job_canvases: jobCanvases, job_names: Object.fromEntries(jobNames) },
        yaml_content: yaml,
        jobs:         buildJobsPayload(jobCanvases as Record<string, { nodes: Node[]; edges: Edge[] }>, jobNames),
      })
      return api.runs.start({ workflow_path: wfQuery.data.path })
    },
    onMutate:  ()     => { applyRunStatus(null, true) },
    onSuccess: (data) => { setLastRun(data); setLogsOpen(true); pollRun(data.run_id) },
    onError:   ()     => { applyRunStatus(null, false); setLogsOpen(true) },
  })

  const runStepMut = useMutation({
    mutationFn: (body: { workflow_path: string; step: string }) => api.runs.start(body),
    onMutate:  ()     => { applyRunStatus(null, true) },
    onSuccess: (data) => { setLastRun(data); setLogsOpen(true); pollRun(data.run_id) },
    onError:   ()     => { applyRunStatus(null, false); setLogsOpen(true) },
  })

  // ── Visionneuse : lecture directe du top N de la destination (aucun re-run) ──
  const viewDataMut = useMutation({
    mutationFn: async (nodeId: string) => {
      const node = nodes.find(n => n.id === nodeId)
      if (!node) throw new Error('Nœud introuvable')
      const cfg = (node.data.params ?? {}) as Record<string, unknown>
      const connType = DEST_TYPE[node.data.nodeType as string] ?? 'csv'
      const isDb = !['csv', 'json', 'parquet'].includes(connType)
      const dest: Record<string, unknown> = isDb
        ? connType === 'mongodb'
          ? { type: connType, connection: { uri: cfg.uri ?? 'mongodb://localhost:27017', database: cfg.database ?? '' }, table: cfg.collection ?? '' }
          : { type: connType, connection: { host: cfg.host ?? 'localhost', port: cfg.port ?? (connType === 'postgresql' ? 5432 : 3306), database: cfg.database ?? '', user: cfg.user ?? '', password: cfg.password ?? '' }, table: cfg.table ?? '' }
        : { type: connType, path: cfg.path ?? '', delimiter: cfg.delimiter }
      // Même résolution de work_dir que « Run Job »
      const projectRoot  = wfQuery.data?.path?.replace(/[\\/]workflows[\\/][^\\/]+$/, '')
      const jobDirOnDisk = (projectRoot && projectRoot !== wfQuery.data?.path && activeJobName)
        ? `${projectRoot}/jobs/${slugify(activeJobName)}`
        : undefined
      const workDir = importedJobPath ?? jobDirOnDisk ?? (wfQuery.data?.path ? wfQuery.data.path.replace(/[\/][^\/]+$/, '') : undefined)
      return api.runs.peek({ dest, limit: loadSettings().output_preview_rows, work_dir: workDir })
    },
    onMutate:  ()     => { setViewer({ loading: true, error: null, cols: [], rows: [] }); setViewerOpen(true) },
    onSuccess: (data) => { setViewer({ loading: false, error: data.error ?? null, cols: data.columns ?? [], rows: data.rows ?? [] }) },
    onError:   (e)    => { setViewer({ loading: false, error: String((e as Error)?.message ?? e), cols: [], rows: [] }) },
  })

  // ── Execute step : exécution partielle jusqu'au nœud cliqué → résultats dans les logs ──
  const stepRunMut = useMutation({
    mutationFn: async (nodeId: string) => {
      const node = nodes.find(n => n.id === nodeId)
      if (!node) throw new Error('Nœud introuvable')
      const cat = getNode(node.data.nodeType as string)?.category
      const tfNodes = nodes.filter(n => getNode(n.data?.nodeType as string)?.category === 'transformation')
      const sorted = [...tfNodes].sort((a, b) => (a.position?.x ?? 0) - (b.position?.x ?? 0))
      let idx: number
      if (cat === 'source') idx = -1
      else if (cat === 'destination') idx = sorted.length - 1
      else {
        idx = sorted.findIndex(n => n.id === nodeId)
        if (idx < 0) idx = sorted.length - 1
      }
      const jobName = activeJobName ?? wfQuery.data?.name ?? 'job'
      const hdrContent = flowToHdr(nodes, edges, jobName)
      const projectRoot  = wfQuery.data?.path?.replace(/[\\/]workflows[\\/][^\\/]+$/, '')
      const jobDirOnDisk = (projectRoot && projectRoot !== wfQuery.data?.path && activeJobName)
        ? `${projectRoot}/jobs/${slugify(activeJobName)}`
        : undefined
      const workDir = importedJobPath ?? jobDirOnDisk ?? (wfQuery.data?.path ? wfQuery.data.path.replace(/[\/][^\/]+$/, '') : undefined)
      return api.runs.startInline({ hdr_content: hdrContent, job_name: `${jobName} · step`, work_dir: workDir, preview_up_to: idx })
    },
    onMutate:  ()     => { applyRunStatus(null, true) },
    onSuccess: (data) => { setLastRun(data); setLogsOpen(true); pollRun(data.run_id) },
    onError:   ()     => { applyRunStatus(null, false); setLogsOpen(true) },
  })

  // Ref stable vers runMut.mutate — utilisé dans les event listeners (évite stale closure)
  const runJobRef = useRef<() => void>(() => {})
  runJobRef.current = () => runMut.mutate()
  const stepRunRef = useRef<(nodeId: string) => void>(() => {})
  stepRunRef.current = (nodeId: string) => stepRunMut.mutate(nodeId)

  // Ref stable pour exécuter un nœud action (powershell/bash) directement
  const runActionRef = useRef<(node: Node<FlowNodeData>) => void>(() => {})
  runActionRef.current = async (node: Node<FlowNodeData>) => {
    const data = node.data as FlowNodeData
    const p    = (data.params as Record<string, string>) ?? {}
    const nt   = data.nodeType ?? ''

    // Validation selon le type
    if (nt === 'action_ssh') {
      if (!p.host?.trim())     { alert('SSH : configurez le champ "Hôte" (double-clic).'); return }
      if (!p.username?.trim()) { alert('SSH : configurez le champ "Utilisateur" (double-clic).'); return }
      if (!p.command?.trim())  { alert('SSH : configurez la commande distante (double-clic).'); return }
    } else if (nt === 'action_webhook') {
      if (!p.url?.trim())    { alert('Webhook : configurez l\'URL (double-clic).'); return }
    } else if (nt === 'action_python') {
      if (!p.script?.trim() && !p.file_path?.trim()) { alert('Python : renseignez le script inline ou le chemin du fichier .py (double-clic).'); return }
    } else {
      if (!p.command?.trim()) { alert('Configurez d\'abord la commande dans le nœud (double-clic → champ Commande).'); return }
    }

    const command = nt === 'action_webhook' ? (p.url ?? '')
                  : nt === 'action_python'  ? (p.script ?? p.file_path ?? '')
                  : (p.command ?? '')

    setLogsOpen(true)
    try {
      const run = await api.runs.startAction({
        node_type:   nt,
        command,
        working_dir: p.working_dir ?? undefined,
        timeout:     p.timeout ? Number(p.timeout) : 60,
        job_name:    wfQuery.data?.name ?? nt,
        params:      (nt === 'action_ssh' || nt === 'action_webhook') ? p : undefined,
      })
      pollRun(run.run_id)
    } catch (err: any) {
      console.error('[runActionRef]', err)
    }
  }

  // ── Import HDR ───────────────────────────────────────────────────────────

  const handleImportHdr = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      if (!text) return
      const result = parseHdr(text)
      if (!result) { alert('Fichier HDR invalide — vérifiez la structure YAML.'); return }
      setNodes(result.nodes as Node<FlowNodeData>[])
      setEdges(result.edges)
      setTimeout(() => rfInstance?.fitView({ padding: 0.15, duration: 350 }), 80)
    }
    reader.readAsText(file)
    // Reset l'input pour permettre re-import du même fichier
    e.target.value = ''
  }, [rfInstance])

  // ── Import job depuis dossier — Scene 2 (crée onglet + nœud sur canvas wf) ─

  const importJobScene2Ref = useRef<HTMLInputElement>(null)

  const handleImportJobScene2 = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return

    try {
      const EXPECTED = ['sources.yaml', 'transformations.yaml', 'destinations.yaml', 'pipeline.yaml']

      // Identifier le dossier racine (premier segment du chemin relatif du 1er fichier)
      const firstFile = files[0] as File & { webkitRelativePath?: string }
      const rootFolder = firstFile.webkitRelativePath?.split('/')[0] ?? 'job'

      // N'indexer que les fichiers directement à la racine du dossier sélectionné
      // (ignore les sous-dossiers pour éviter les collisions de noms)
      const byName: Record<string, File> = {}
      for (const f of files) {
        const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath ?? f.name
        const parts = rel.split('/')
        // Fichier à la racine du dossier sélectionné : 2 segments (folder/file.yaml)
        if (parts.length === 2 && EXPECTED.includes(parts[1].toLowerCase())) {
          byName[parts[1].toLowerCase()] = f
        }
      }

      const missing = EXPECTED.filter(n => !byName[n])
      if (missing.length) {
        alert(`Fichiers manquants à la racine du dossier :\n${missing.join('\n')}`)
        return
      }

      Promise.all(EXPECTED.map(name =>
        new Promise<string>((res, rej) => {
          const r = new FileReader()
          r.onload  = ev => res(ev.target?.result as string)
          r.onerror = rej
          r.readAsText(byName[name])
        })
      )).then(([sources, transformations, destinations, pipeline]) => {
        try {
          const yamls: JobSectionYamls = { sources, transformations, destinations, pipeline }
          const model = sectionYamlsToJobModel(yamls, rootFolder)
          if (!model) { alert('Structure YAML invalide — vérifiez les 4 fichiers.'); return }
          const { nodes: jobNodes, edges: jobEdges } = jobModelToFlow(model)

          const newJobId   = `job_${Date.now()}`
          const newJobName = rootFolder

          // Sauvegarder le canvas du job dans la ref
          jobCanvasRef.current.set(newJobId, { nodes: jobNodes, edges: jobEdges })
          setJobNames(prev => { const next = new Map(prev); next.set(newJobId, newJobName); return next })

          // Calculer la position sur le canvas Scene 2
          const wfNodes = sceneMode === 'workflow' ? nodes : (wfSnapshot?.nodes ?? []) as Node<FlowNodeData>[]
          const maxX = wfNodes.length > 0 ? Math.max(...wfNodes.map(n => n.position.x)) + 220 : 200
          const avgY = wfNodes.length > 0 ? wfNodes.reduce((s, n) => s + n.position.y, 0) / wfNodes.length : 200

          const newJobNode: Node<FlowNodeData> = {
            id: newJobId,
            type: 'hydraNode',
            position: { x: maxX, y: avgY },
            data: {
              label:    newJobName,
              nodeType: 'job',
              stepName: newJobId,
              jobRef:   newJobId,
              onFailure: 'fail',
              enabled:   true,
            } as FlowNodeData,
          }

          // Si on est en Scene 2 : ajouter directement sur le canvas courant
          // Si on est en Scene 1 : mettre à jour le snapshot wf
          if (sceneMode === 'workflow') {
            pushHistory(nodes, edges)
            setNodes(nds => [...nds, newJobNode])
            setTimeout(() => rfInstance?.fitView({ padding: 0.15, duration: 350 }), 80)
          } else {
            setWfSnapshot(prev => ({
              nodes: [...(prev?.nodes ?? []), newJobNode],
              edges: prev?.edges ?? [],
            }))
          }
        } catch (err) {
          console.error('[importJobScene2] erreur traitement YAML:', err)
          alert(`Erreur lors du traitement des fichiers YAML :\n${err instanceof Error ? err.message : String(err)}`)
        }
      }).catch(err => {
        console.error('[importJobScene2] erreur lecture fichiers:', err)
        alert('Erreur de lecture des fichiers — vérifiez les permissions.')
      })
    } catch (err) {
      console.error('[importJobScene2] erreur inattendue:', err)
      alert(`Erreur inattendue :\n${err instanceof Error ? err.message : String(err)}`)
    }
  }, [nodes, edges, sceneMode, wfSnapshot, pushHistory, rfInstance])

  // ── Import depuis dossier job (4 fichiers YAML) — Scene 1 ────────────────

  const handleImportFolder = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (!files.length) return

    const EXPECTED = ['sources.yaml', 'transformations.yaml', 'destinations.yaml', 'pipeline.yaml']
    const byName: Record<string, File> = {}
    for (const f of files) {
      const base = f.name.toLowerCase()
      if (EXPECTED.includes(base)) byName[base] = f
    }

    const missing = EXPECTED.filter(n => !byName[n])
    if (missing.length) {
      alert(`Fichiers manquants dans le dossier :\n${missing.join('\n')}`)
      e.target.value = ''; return
    }

    // Extraire le nom du dossier depuis le chemin relatif du premier fichier
    const folderName = (files[0] as File & { webkitRelativePath?: string })
      .webkitRelativePath?.split('/')[0] ?? ''

    // Lire les 4 fichiers en parallèle
    Promise.all(EXPECTED.map(name =>
      new Promise<string>((res, rej) => {
        const r = new FileReader()
        r.onload  = ev => res(ev.target?.result as string)
        r.onerror = rej
        r.readAsText(byName[name])
      })
    )).then(([sources, transformations, destinations, pipeline]) => {
      const yamls: JobSectionYamls = { sources, transformations, destinations, pipeline }
      const model = sectionYamlsToJobModel(yamls, 'imported_job')
      if (!model) { alert('Structure YAML invalide — vérifiez les 4 fichiers.'); return }
      const { nodes: n, edges: ex } = jobModelToFlow(model)
      pushHistory(nodes, edges)
      setNodes(n as Node<FlowNodeData>[])
      setEdges(ex)
      setTimeout(() => rfInstance?.fitView({ padding: 0.15, duration: 350 }), 80)

      // Résoudre le chemin absolu côté serveur pour la résolution des chemins relatifs à l'exécution
      if (folderName) {
        api.fs.findJobFolder(folderName).then(res => {
          if (res.found && res.path) {
            setImportedJobPath(res.path)
          } else {
            setImportedJobPath(undefined)
          }
        }).catch(() => setImportedJobPath(undefined))
      }
    }).catch(() => alert('Erreur de lecture des fichiers.'))

    e.target.value = ''
  }, [rfInstance, pushHistory])

  // ── Raccourcis clavier globaux ────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey
      const tag  = (e.target as HTMLElement).tagName
      const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'

      // Ctrl+S — sauvegarde
      if (ctrl && e.key === 's') { e.preventDefault(); saveMut.mutate(); return }

      // Ctrl+Z — undo
      if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); handleUndo(); return }

      // Ctrl+Y ou Ctrl+Shift+Z — redo
      if ((ctrl && e.key === 'y') || (ctrl && e.shiftKey && e.key === 'z')) {
        e.preventDefault(); handleRedo(); return
      }

      // Ctrl+A — sélectionner tout
      if (ctrl && e.key === 'a' && !inInput) {
        e.preventDefault()
        setNodes(nds => nds.map(n => ({ ...n, selected: true })))
        setEdges(eds => eds.map(e => ({ ...e, selected: true })))
        return
      }

      // Delete / Backspace — suppression manuelle (deleteKeyCode={null} sur ReactFlow)
      if ((e.key === 'Delete' || e.key === 'Backspace') && !inInput) {
        e.preventDefault()
        const inst = rfInstanceRef.current
        if (!inst) return
        const selNodes = (inst.getNodes() as Node<FlowNodeData>[]).filter(n => n.selected)
        const selEdges = inst.getEdges().filter(e2 => e2.selected)
        if (selNodes.length === 0 && selEdges.length === 0) return
        pushHistory(inst.getNodes() as Node<FlowNodeData>[], inst.getEdges() as Edge[])
        // deleteElements => declenche onNodesDelete (purge job unifiee + choix)
        inst.deleteElements({ nodes: selNodes.map(n => ({ id: n.id })), edges: selEdges.map(e2 => ({ id: e2.id })) })
        return
      }

      // H — mode pan
      if (e.key === 'h' || e.key === 'H') {
        if (!inInput) { setInteractionMode('pan'); return }
      }
      // V — mode sélection
      if (e.key === 'v' || e.key === 'V') {
        if (!inInput) { setInteractionMode('select'); return }
      }
      // Escape — retour pan + désélection
      if (e.key === 'Escape') {
        setInteractionMode('pan')
        setNodes(nds => nds.map(n => ({ ...n, selected: false })))
        setEdges(eds => eds.map(e2 => ({ ...e2, selected: false })))
        setMultiSel({ nodes: [], edges: [] })
        setSelectedNode(null)
        setContextMenu(null)
        return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveMut, handleUndo, handleRedo, edges, pushHistory])

  // ── Render ────────────────────────────────────────────────────────────────

  if (wfQuery.isLoading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>

  if (wfQuery.isError) return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <AlertTriangle size={40} style={{ color: 'var(--error)' }} />
      <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
        Impossible de charger le workflow
      </p>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        Vérifiez que le backend est démarré (<code>hdrctl serve</code>) et rafraîchissez la page.
      </p>
    </div>
  )

  return (
    <div className="flex flex-col h-full -m-6 overflow-hidden" style={{ height: 'calc(100vh - 56px)' }}>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 shrink-0"
        style={{ background: 'var(--bg-card)', borderBottom: '1px solid var(--bg-border)' }}>

        {/* Breadcrumb : Scene 1 → ← wfName / jobName | Scene 2 → ← wfName */}
        <Link to={`/projects/${projectId}`}
          className="flex items-center gap-1 text-xs hover:opacity-70 transition-opacity"
          style={{ color: 'var(--text-secondary)', marginRight: 2 }}>
          <ChevronLeft size={14} /> {wfQuery.data?.name ?? 'Workflow'}
        </Link>
        {isJobScene && activeJobName && (
          <>
            <span style={{ color: 'var(--text-muted)', fontSize: 11, marginRight: 4 }}>/</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--primary)', marginRight: 8 }}>
              {activeJobName}
            </span>
          </>
        )}

        <div className="flex items-center gap-1.5 text-xs mr-2" style={{ color: 'var(--text-muted)' }}>
          <GitBranch size={12} />
          <span className="font-mono">{nodes.length} nodes · {edges.length} edges</span>
        </div>

        {validationErrors.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg"
            style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--error)' }}>
            <AlertTriangle size={12} /> {validationErrors[0]}
          </div>
        )}
        {validationErrors.length === 0 && nodes.length > 0 && (
          <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--success)' }}>
            <CheckCircle2 size={12} /> Valid
          </div>
        )}

        <div className="flex-1" />

        {replaceNodeId && (
          <div className="text-xs px-3 py-1 rounded-lg animate-pulse"
            style={{ background: 'var(--primary-subtle)', color: 'var(--primary)' }}>
            Drag a node from the palette to replace
          </div>
        )}

        {/* Undo / Redo */}
        <button onClick={handleUndo} disabled={!canUndo}
          className="btn-secondary text-xs !py-1.5" title="Annuler (Ctrl+Z)"
          style={{ opacity: canUndo ? 1 : 0.35 }}>
          <Undo2 size={13} />
        </button>
        <button onClick={handleRedo} disabled={!canRedo}
          className="btn-secondary text-xs !py-1.5" title="Rétablir (Ctrl+Y)"
          style={{ opacity: canRedo ? 1 : 0.35 }}>
          <Redo2 size={13} />
        </button>

        {/* Import — inputs cachés (toujours montés pour garder les refs actives) */}
        <input ref={importInputRef}  type="file" accept=".hdr,.yaml,.yml" onChange={handleImportHdr}    style={{ display: 'none' }} />
        <input ref={importFolderRef} type="file" onChange={handleImportFolder} style={{ display: 'none' }}
          // @ts-expect-error webkitdirectory non standard mais supporté par tous les navigateurs modernes
          webkitdirectory="" mozdirectory="" />
        <input ref={importJobScene2Ref} type="file" onChange={handleImportJobScene2} style={{ display: 'none' }}
          // @ts-expect-error webkitdirectory
          webkitdirectory="" mozdirectory="" />

        {/* Import — bouton dropdown : visible uniquement en Scene 2 (Workflow configuration) */}
        {!isJobScene && (
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setImportMenuOpen(v => !v)}
              className="btn-secondary text-xs !py-1.5"
              title="Importer un job dans le workflow"
            >
              <Upload size={13} />
              Import
              <ChevronDown size={11} style={{ marginLeft: 2 }} />
            </button>

            {importMenuOpen && (
              <>
                <div
                  style={{ position: 'fixed', inset: 0, zIndex: 49 }}
                  onClick={() => setImportMenuOpen(false)}
                />
                <div style={{
                  position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 50,
                  background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
                  borderRadius: 8, minWidth: 220, boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                  overflow: 'hidden',
                }}>
                  {/* Scene 2 : import job → nouvel onglet + nœud canvas */}
                  <button
                    onClick={() => { setImportMenuOpen(false); importJobScene2Ref.current?.click() }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      width: '100%', padding: '10px 14px',
                      background: 'transparent', border: 'none',
                      color: 'var(--text-primary)', cursor: 'pointer', textAlign: 'left', fontSize: 12,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <FolderOpen size={14} style={{ color: '#8b5cf6', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontWeight: 600 }}>Importer un job</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
                        Sélectionner un dossier job (4 YAML) → nœud sur le canvas
                      </div>
                    </div>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        <button
          onClick={() => setCodeOpen(v => !v)}
          className="btn-secondary text-xs !py-1.5"
          title={isJobScene ? 'Toggle HDR panel' : 'Toggle YAML panel'}
          style={codeOpen ? { background: 'var(--primary-subtle)', color: 'var(--primary)', borderColor: 'var(--primary)' } : {}}
        >
          <Code2 size={13} />
          {isJobScene ? 'HDR' : 'Code'}
        </button>

        <button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending || validationErrors.length > 0 || nodes.length === 0}
          className="btn-primary text-xs !py-1.5"
          title={isJobScene ? 'Run Job (Space)' : 'Run Workflow'}
          style={{ background: 'var(--success)', borderColor: 'var(--success)' }}
        >
          {runMut.isPending ? <Spinner size="sm" /> : <Play size={13} fill="currentColor" />}
          {isJobScene ? 'Run Job' : 'Run Workflow'}
        </button>

        <button onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending || validationErrors.length > 0}
          className="btn-primary text-xs !py-1.5"
          title={saveStatus === 'error' ? 'Erreur sauvegarde' : 'Sauvegarder (Ctrl+S)'}
          style={saveStatus === 'error' ? { background: 'var(--error)' } : {}}
        >
          {saveMut.isPending ? <Spinner size="sm" /> : <Save size={13} />}
          {saveStatus === 'saved' ? 'Saved ✓' : 'Save'}
        </button>

      </div>{/* /toolbar */}

      {/* ── Diagnostics manifests (fichier + ligne) ─────────────────────── */}
      {loadIssues.length > 0 && (
        <div style={{
          flexShrink: 0, padding: '8px 16px',
          background: 'rgba(245,158,11,0.08)',
          borderBottom: '1px solid rgba(245,158,11,0.35)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700, color: 'var(--warning)' }}>
            <AlertTriangle size={13} />
            Fichiers manifest invalides — les éléments concernés ont été ignorés
            <div style={{ flex: 1 }} />
            <button onClick={() => setLoadIssues([])} title="Masquer"
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 13, padding: 2 }}>✕</button>
          </div>
          {loadIssues.map((m, i) => (
            <div key={i} style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--warning)', marginTop: 3, opacity: 0.9 }}>
              {m}
            </div>
          ))}
        </div>
      )}

      {/* ── Scene switcher tabs ──────────────────────────────────────────── */}
      <div style={{
        display: 'flex', flexShrink: 0, height: 36,
        borderBottom: '1px solid var(--bg-border)',
        background: 'var(--bg-card)',
      }}>
        {([
          { key: 'jobs',     label: 'Jobs configuration' },
          { key: 'workflow', label: 'Workflow configuration' },
        ] as { key: SceneMode; label: string }[]).map(tab => (
          <button
            key={tab.key}
            onClick={() => {
              if (tab.key === 'workflow') { switchToWorkflowScene(); return }
              const jid = activeJobId ?? [...jobNames.keys()][0] ?? null
              if (jid) { switchToJobScene(jid); return }
              // Aucun job — basculer en mode jobs avec canvas vide
              if (sceneMode === 'workflow') setWfSnapshot({ nodes: [...nodes], edges: [...edges] })
              setNodes([]); setEdges([]); setSceneMode('jobs')
            }}
            style={{
              flex: 'none', padding: '0 20px', border: 'none', cursor: 'pointer',
              fontWeight: sceneMode === tab.key ? 700 : 400,
              fontSize: 12,
              background: sceneMode === tab.key ? 'var(--primary-subtle)' : 'transparent',
              color: sceneMode === tab.key ? 'var(--primary)' : 'var(--text-secondary)',
              borderBottom: sceneMode === tab.key ? '2px solid var(--primary)' : '2px solid transparent',
              transition: 'all 0.15s', letterSpacing: 0.3,
            }}
            onMouseEnter={e => { if (sceneMode !== tab.key) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-hover)' }}
            onMouseLeave={e => { if (sceneMode !== tab.key) (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
          >
            {tab.label}
          </button>
        ))}
      </div>{/* /scene-tabs */}

      {/* ── Main area ─────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden min-h-0" style={{ position: 'relative' }}>

        {/* Multi-selection / single-node floating toolbar */}
        {(multiSel.nodes.length > 0 || multiSel.edges.length > 0) && (
          <div style={{
            position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
            zIndex: 30, display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bg-card)', border: '1px solid var(--bg-border)',
            borderRadius: 10, padding: '6px 12px', boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            fontSize: 12, color: 'var(--text-secondary)',
          }}>
            {multiSel.nodes.length > 0 && (
              <span style={{ fontWeight: 600, color: 'var(--primary)' }}>
                {multiSel.nodes.length} node{multiSel.nodes.length > 1 ? 's' : ''}
              </span>
            )}
            {multiSel.edges.length > 0 && (
              <span style={{ fontWeight: 600, color: 'var(--text-muted)' }}>
                {multiSel.edges.length} edge{multiSel.edges.length > 1 ? 's' : ''}
              </span>
            )}

            {/* Bouton Terminal — nœud bash ou powershell sélectionné */}
            {multiSel.nodes.length === 1 && (() => {
              const nodeType = multiSel.nodes[0].data?.nodeType as string
              if (nodeType !== 'action_bash' && nodeType !== 'action_powershell' && nodeType !== 'action_ssh') return null
              const sh = nodeType === 'action_bash' ? 'bash' : nodeType === 'action_ssh' ? 'ssh' : 'powershell'
              const cmd = (multiSel.nodes[0].data?.params as any)?.command as string | undefined
              return (
                <>
                  <div style={{ width: 1, height: 16, background: 'var(--bg-border)' }} />
                  <button
                    onClick={() => { setTerminalShell(sh); setBottomTab('terminal'); setLogsOpen(true) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      background: sh === 'powershell' ? 'rgba(37,99,235,0.15)' : 'rgba(22,163,74,0.15)',
                      color:      sh === 'powershell' ? '#79c0ff' : '#56d364',
                      border:     sh === 'powershell' ? '1px solid rgba(37,99,235,0.4)' : '1px solid rgba(22,163,74,0.4)',
                      borderRadius: 6, padding: '3px 8px', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                    }}
                    title={`Ouvrir terminal ${sh}`}
                  >
                    <Terminal size={11} />
                    {sh === 'powershell' ? 'PowerShell' : 'Bash'}
                  </button>
                </>
              )
            })()}

            {/* Grouper la sélection dans un Sequence Container */}
            {multiSel.nodes.filter(n => !isContainerNode(n) && !n.parentId).length >= 1 && (
              <>
                <div style={{ width: 1, height: 16, background: 'var(--bg-border)' }} />
                <button
                  onClick={groupSelectionIntoContainer}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    background: 'rgba(245,158,11,0.14)', color: 'var(--warning)',
                    border: '1px solid rgba(245,158,11,0.35)', borderRadius: 6,
                    padding: '3px 8px', fontSize: 11, cursor: 'pointer', fontWeight: 600,
                  }}
                  title="Regrouper dans un Sequence Container"
                >
                  <Boxes size={12} /> Grouper
                </button>
              </>
            )}

            <div style={{ width: 1, height: 16, background: 'var(--bg-border)' }} />
            <button
              onClick={deleteSelection}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: 'rgba(239,68,68,0.12)', color: 'var(--error)',
                border: '1px solid rgba(239,68,68,0.3)', borderRadius: 6,
                padding: '3px 8px', fontSize: 11, cursor: 'pointer', fontWeight: 600,
              }}
              title="Supprimer la sélection (Delete)"
            >
              <Trash2 size={12} /> Delete
            </button>
          </div>
        )}

        <NodePalette
          onDragStart={onDragStart}
          onJobDragStart={onJobDragStart}
          replaceMode={replaceNodeId != null}
          onCancelReplace={() => setReplaceNodeId(null)}
          sceneMode={sceneMode}
          jobsList={[...jobNames.entries()].map(([id, name]) => ({ id, name }))}
          onJobContextMenu={onJobContextMenu}
        />

        <CanvasToolbox
          interactionMode={interactionMode}
          onModeChange={setInteractionMode}
          canUndo={canUndo}
          canRedo={canRedo}
          onUndo={handleUndo}
          onRedo={handleRedo}
          minimapVisible={minimapVisible}
          onToggleMinimap={() => setMinimapVisible(v => !v)}
          logsVisible={logsOpen}
          onToggleLogs={() => setLogsOpen(v => !v)}
        />

        {/* Canvas */}
        <div ref={rfWrapper} style={{ flex: 1, position: 'relative' }}>

          <SceneContext.Provider value={sceneMode}>
          <ReactFlow
            nodes={nodes}
            edges={displayEdges}
            onNodesChange={onNodesChange as any}
            onEdgesChange={onEdgesChange}
            onNodesDelete={onNodesDelete}
            onConnect={onConnect}
            onEdgeDoubleClick={onEdgeDoubleClick}
            onInit={setRfInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onNodeDragStop={onNodeDragStop}
            onNodeContextMenu={onNodeContextMenu}
            onPaneClick={() => setContextMenu(null)}
            onSelectionChange={onSelectionChange}
            nodeTypes={NODE_TYPES}
            fitView
            deleteKeyCode={null}
            panOnDrag={interactionMode === 'pan'}
            selectionOnDrag={interactionMode === 'select'}
            multiSelectionKeyCode="Shift"
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--canvas-dot)" />
            <Controls />
            {minimapVisible && <MiniMap />}
            {/* Logo watermark — centré dans le viewport canvas, toujours visible */}
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              pointerEvents: 'none', zIndex: 0,
            }}>
              <img
                src="/Hydra.png"
                alt="Hydra"
                style={{ width: 550, opacity: nodes.length === 0 ? 0.18 : 0.05, userSelect: 'none', transition: 'opacity 0.4s' }}
                draggable={false}
              />
              {nodes.length === 0 && (
                <>
                  <span style={{
                    marginTop: 10, fontSize: 12, fontWeight: 700, letterSpacing: 3,
                    opacity: 0.2, color: 'var(--text-primary)', userSelect: 'none',
                  }}>
                    HYDRA STUDIO
                  </span>
                  <span style={{
                    marginTop: 4, fontSize: 11, opacity: 0.15,
                    color: 'var(--text-muted)', userSelect: 'none',
                  }}>
                    Drag nodes from the palette to get started
                  </span>
                </>
              )}
            </div>

            {/* ── Bouton Run flottant — centre bas du canvas ── */}
            {(
              <div style={{
                position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
                zIndex: 20, pointerEvents: 'auto',
              }}>
                <button
                  onClick={() => runMut.mutate()}
                  disabled={runMut.isPending || validationErrors.length > 0}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '10px 24px', borderRadius: 30,
                    background: validationErrors.length > 0 ? 'var(--bg-hover)' : 'var(--success)',
                    color: validationErrors.length > 0 ? 'var(--text-muted)' : '#fff',
                    border: 'none', fontSize: 13, fontWeight: 700,
                    boxShadow: '0 4px 20px rgba(0,0,0,0.35)',
                    cursor: runMut.isPending || validationErrors.length > 0 ? 'not-allowed' : 'pointer',
                    transition: 'transform 0.15s, box-shadow 0.15s',
                    letterSpacing: '0.03em',
                  }}
                  onMouseEnter={e => {
                    if (!runMut.isPending && validationErrors.length === 0)
                      (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'none' }}
                >
                  {runMut.isPending
                    ? <><Spinner size="sm" /> Running…</>
                    : <><Play size={14} fill="currentColor" /> {isJobScene ? 'Run Job' : 'Run Workflow'}</>}
                </button>
              </div>
            )}
          </ReactFlow>
          </SceneContext.Provider>
        </div>

        {/* Properties panel */}
        {selectedNode && !dialogNode && (
          <PropertiesPanel
            node={selectedNode}
            focusRename={renameNodeId === selectedNode.id || undefined}
            onClose={() => { setSelectedNode(null); setRenameNodeId(null) }}
            onChange={onNodeDataChange}
          />
        )}

        {/* Context menu */}
        {contextMenu && (
          <NodeContextMenu
            menu={contextMenu}
            isJobScene={isJobScene}
            onClose={() => setContextMenu(null)}
            onAttachToContainer={attachToContainer}
            onDetachFromContainer={detachFromContainer}
            onViewData={(nodeId) => { setContextMenu(null); viewDataMut.mutate(nodeId) }}
            onOpenPanel={(nodeId) => {
              const n = nodes.find(x => x.id === nodeId)
              if (n) setDialogNode(n)
              setContextMenu(null)
            }}
            onRename={(nodeId) => {
              setRenameNodeId(nodeId)
              const n = nodes.find(x => x.id === nodeId)
              if (n) setSelectedNode(n)
              setContextMenu(null)
            }}
            onReplace={(nodeId) => {
              setReplaceNodeId(nodeId)
              setContextMenu(null)
            }}
            onRunStep={(nodeId) => {
              const n = nodes.find(x => x.id === nodeId)
              if (!n) { setContextMenu(null); return }
              if (isJobScene) { stepRunMut.mutate(nodeId); setContextMenu(null); return }
              if (wfQuery.data?.path) {
                runStepMut.mutate({ workflow_path: wfQuery.data.path, step: (n.data as FlowNodeData).stepName })
              }
              setContextMenu(null)
            }}
          />
        )}

        {/* Config dialog */}
        {dialogNode && (
          <NodeConfigDialog
            node={dialogNode}
            onClose={() => setDialogNode(null)}
            onSave={(id, patch) => onNodeDataChange(id, patch)}
            joinSources={nodes
              .filter(n => (n.data.nodeType as string ?? '').startsWith('source_'))
              .map(n => ({ id: n.id, label: (n.data.label as string) || (n.data.stepName as string) || (n.data.nodeType as string) }))}
          />
        )}

        {/* YAML / HDR code panel */}
        {codeOpen && (
          <YamlCodePanel
            nodes={nodes}
            edges={edges}
            meta={{
              name: wfQuery.data?.name ?? 'workflow',
              triggerType: (wfQuery.data?.trigger_type ?? 'manual') as 'manual' | 'schedule' | 'webhook',
              cron: wfQuery.data?.cron,
            }}
            onApply={(n, e) => { setNodes(n); setEdges(e) }}
            onClose={() => setCodeOpen(false)}
            mode={isJobScene ? 'job' : 'workflow'}
          />
        )}

        {/* ── Visionneuse de données (View data) ──────────── */}
        {viewerOpen && (
          <DataViewerModal
            rows={viewer.rows}
            cols={viewer.cols}
            loading={viewer.loading}
            error={viewer.error}
            limitRows={loadSettings().output_preview_rows}
            onClose={() => setViewerOpen(false)}
          />
        )}

      </div>{/* /main area */}

      {/* ── Volet Logs (bas, redimensionnable) ───────────────────────────── */}
      {logsOpen && (
        <div style={{
          height: logsPanelH, flexShrink: 0, position: 'relative',
          borderTop: '1px solid var(--bg-border)', background: 'var(--bg-card)',
          display: 'flex', flexDirection: 'column',
        }}>
          {/* Splitter horizontal */}
          <div
            title="Glisser pour redimensionner"
            style={{ position: 'absolute', top: -4, left: 0, right: 0, height: 8, cursor: 'row-resize', zIndex: 10 }}
            onMouseDown={e => {
              e.preventDefault()
              const y0 = e.clientY, h0 = logsPanelH
              const onMove = (me: MouseEvent) => setLogsPanelH(Math.max(120, Math.min(520, h0 - (me.clientY - y0))))
              const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
              window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp)
            }}
          />
          {/* Header */}
          <div className="flex items-center gap-2 px-3 py-1.5 shrink-0" style={{ borderBottom: '1px solid var(--bg-border)' }}>
            {([['logs', 'LOGS'], ['params', 'PARAMETERS'], ['terminal', 'TERMINAL']] as const).map(([key, label]) => (
              <button key={key} type="button" onClick={() => setBottomTab(key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 700, letterSpacing: 1, fontFamily: 'monospace',
                  padding: '2px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: bottomTab === key ? 'var(--bg-hover)' : 'transparent',
                  color: bottomTab === key ? 'var(--primary)' : 'var(--text-muted)',
                }}>
                <Terminal size={12} /> {label}
              </button>
            ))}
            {bottomTab === 'logs' && lastRun && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '1px 8px', borderRadius: 10,
                color: lastRun.status === 'success' ? 'var(--success)' : lastRun.status === 'failed' ? 'var(--error)' : 'var(--warning)',
                background: lastRun.status === 'success' ? 'rgba(34,197,94,0.12)' : lastRun.status === 'failed' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
              }}>
                {lastRun.status.toUpperCase()}
              </span>
            )}
            <div className="flex-1" />
            <button onClick={() => setLogsOpen(false)} className="btn-secondary text-xs !py-0.5" title="Fermer">✕</button>
          </div>
          {/* Contenu */}
          <div style={{ flex: 1, overflow: bottomTab === 'params' ? 'auto' : 'hidden', padding: bottomTab === 'terminal' ? 0 : '6px 10px' }}>
            {bottomTab === 'terminal' ? (
              <TerminalPanel shell={(terminalShell === 'ssh' ? null : terminalShell) ?? defaultShell} onClose={() => setBottomTab('logs')} />
            ) : bottomTab === 'params' ? (
              <ParametersPanel projectId={projectId} accent={'var(--primary)'} />
            ) : lastRun
              ? <LogViewer lines={logLines} maxHeight={logsPanelH - 70} title={lastRun.workflow_name} />
              : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 12, fontFamily: 'monospace' }}>
                  Lancez un job ou un workflow pour voir les logs.
                </div>}
          </div>
        </div>
      )}

      {/* ── Job tab bar (Scene 1 uniquement) ─────────────────────────────── */}
      {isJobScene && (
        <div style={{
          display: 'flex', alignItems: 'stretch', flexShrink: 0, height: 32,
          borderTop: '1px solid var(--bg-border)', background: 'var(--bg-card)',
          fontSize: 11, overflow: 'hidden', position: 'relative',
        }}>
          {[...jobNames.entries()].map(([jobId, jobName]) => {
            const isActive    = jobId === activeJobId
            const isRenaming  = renamingJobId === jobId
            return (
              <div
                key={jobId}
                onClick={() => !isRenaming && switchToJobScene(jobId)}
                title="Double-clic pour renommer"
                onDoubleClick={() => setRenamingJobId(jobId)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '0 6px 0 14px',
                  background: isActive ? 'var(--primary-subtle)' : 'transparent',
                  color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                  borderRight: '1px solid var(--bg-border)',
                  boxShadow: isActive ? 'inset 0 -2px 0 var(--primary)' : 'none',
                  fontWeight: isActive ? 700 : 400,
                  cursor: isRenaming ? 'text' : (isActive ? 'default' : 'pointer'),
                  whiteSpace: 'nowrap', flexShrink: 0,
                  transition: 'background 0.15s, color 0.15s',
                  minWidth: 80, userSelect: 'none',
                }}
              >
                <Circle size={8} fill={isActive ? 'currentColor' : 'none'} style={{ flexShrink: 0 }} />
                {isRenaming ? (
                  <input
                    autoFocus
                    defaultValue={jobName}
                    style={{
                      background: 'transparent', border: 'none', outline: 'none',
                      color: 'var(--primary)', fontSize: 11, fontWeight: 700,
                      width: Math.max(60, jobName.length * 8), fontFamily: 'inherit',
                    }}
                    onBlur={e => renameJob(jobId, e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter')  renameJob(jobId, (e.target as HTMLInputElement).value)
                      if (e.key === 'Escape') setRenamingJobId(null)
                    }}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <span>{jobName}</span>
                )}
                <button
                  onClick={e => {
                    e.stopPropagation()
                    const rect = e.currentTarget.getBoundingClientRect()
                    setTabMenu(prev => prev?.jobId === jobId ? null : { jobId, x: rect.left, y: rect.top })
                  }}
                  title="Options"
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: isActive ? 'var(--primary)' : 'var(--text-muted)',
                    opacity: 0.6, transition: 'opacity 0.15s, background 0.15s',
                    padding: 0, marginLeft: 2,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'var(--bg-hover)' }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = '0.6'; e.currentTarget.style.background = 'transparent' }}
                ><MoreHorizontal size={12} /></button>
              </div>
            )
          })}

          {/* Bouton + : nouveau job */}
          <button
            onClick={addJob}
            title="Ajouter un nouveau job"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '0 12px', background: 'transparent', color: 'var(--text-muted)',
              border: 'none', cursor: 'pointer', borderRadius: 0,
              fontSize: 18, fontWeight: 300, lineHeight: 1,
              flexShrink: 0, transition: 'color 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
          >+</button>

          <div style={{ flex: 1 }} />
        </div>
      )}

      {/* ── Menu contextuel onglet job (Scene 1) ────────────────────────────── */}
      {tabMenu && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 49 }}
            onClick={() => setTabMenu(null)}
          />
          <div style={{
            position: 'fixed', left: tabMenu.x, top: tabMenu.y - 72,
            zIndex: 50, background: 'var(--bg-card)',
            border: '1px solid var(--bg-border)', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.3)', minWidth: 160, overflow: 'hidden',
          }}>
            <button
              onClick={() => { setRenamingJobId(tabMenu.jobId); setTabMenu(null) }}
              style={{
                width: '100%', padding: '8px 14px', background: 'transparent',
                border: 'none', cursor: 'pointer', textAlign: 'left',
                fontSize: 12, color: 'var(--text-primary)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <Pencil size={13} /> Renommer
            </button>
            <button
              onClick={() => archiveJob(tabMenu.jobId)}
              style={{ width: '100%', padding: '8px 14px', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 12, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <Archive size={13} /> Archiver
            </button>
            <div style={{ height: 1, background: 'var(--bg-border)' }} />
            <button
              onClick={() => deleteJob(tabMenu.jobId)}
              style={{
                width: '100%', padding: '8px 14px', background: 'transparent',
                border: 'none', cursor: 'pointer', textAlign: 'left',
                fontSize: 12, color: 'var(--error)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <Trash2 size={13} /> Supprimer
            </button>
          </div>
        </>
      )}

      {/* ── Menu contextuel nœud Job (Scene 2 / Workflow canvas) ───────────── */}
      {jobScene2Menu && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 49 }}
            onClick={() => setJobScene2Menu(null)}
          />
          <div style={{
            position: 'fixed', left: jobScene2Menu.x, top: jobScene2Menu.y,
            zIndex: 50, background: 'var(--bg-card)',
            border: '1px solid var(--bg-border)', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.3)', minWidth: 160, overflow: 'hidden',
          }}>
            <button
              onClick={() => {
                const node = nodes.find(n => n.id === jobScene2Menu.nodeId)
                if (node) { const jid = (node.data as any).jobRef ?? node.id; switchToJobScene(jid) }
                setJobScene2Menu(null)
              }}
              style={{
                width: '100%', padding: '8px 14px', background: 'transparent',
                border: 'none', cursor: 'pointer', textAlign: 'left',
                fontSize: 12, color: 'var(--text-primary)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <ArrowLeft size={13} /> Ouvrir dans Jobs config
            </button>
            <div style={{ height: 1, background: 'var(--bg-border)' }} />
            <button
              onClick={() => duplicateJobInScene2(jobScene2Menu.nodeId)}
              style={{
                width: '100%', padding: '8px 14px', background: 'transparent',
                border: 'none', cursor: 'pointer', textAlign: 'left',
                fontSize: 12, color: 'var(--text-primary)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <Copy size={13} /> Dupliquer
            </button>
          </div>
        </>
      )}

    </div>
  )
}

export default function WorkflowEditor() {
  return (
    <ReactFlowProvider>
      <WorkflowEditorInner />
    </ReactFlowProvider>
  )
}
