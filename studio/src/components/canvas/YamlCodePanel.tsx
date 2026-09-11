/**
 * YamlCodePanel — Panneau YAML bidirectionnel pour le canvas Hydra.
 * Éditeur CodeMirror 6 : syntax highlighting YAML, numéros de ligne,
 * fold, copier/coller/couper natifs, thème sombre.
 *
 * Mode 'job'      → 4 onglets (Sources / Transformations / Destinations / Pipeline)
 * Mode 'workflow' → éditeur monolithique (inchangé)
 */
import { useEffect, useRef, useState, useCallback, MouseEvent as ReactMouseEvent } from 'react'
import type { Node, Edge } from '@xyflow/react'
import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { oneDark } from '@codemirror/theme-one-dark'
import {
  X, Copy, Check, Code2, AlertCircle, RefreshCw,
  Wand2, ExternalLink, Library, Cpu,
} from 'lucide-react'
import {
  flowToWorkflow,
  workflowToYAMLString,
  workflowToFlow,
  parseWorkflowYAML,
  type FlowNodeData,
  type WorkflowYAML,
} from '@/lib/workflowSerializer'
import {
  flowToHdr, parseHdr,
  flowToJobModel, jobModelToSectionYamls, sectionYamlsToJobModel, jobModelToFlow,
  type JobSectionYamls,
} from '@/lib/hdrSerializer'

// ── Constantes onglets ────────────────────────────────────────────────────────

type JobTab = 'sources' | 'transformations' | 'destinations' | 'pipeline'
const JOB_TABS: { key: JobTab; label: string; color: string }[] = [
  { key: 'sources',         label: 'Sources',         color: '#3b82f6' },
  { key: 'transformations', label: 'Transformations',  color: '#a855f7' },
  { key: 'destinations',    label: 'Destinations',     color: '#10b981' },
  { key: 'pipeline',        label: 'Pipeline',         color: '#f59e0b' },
]

const EMPTY_SECTIONS: JobSectionYamls = {
  sources:         'version: "1.0"\nsources: {}\n',
  transformations: 'version: "1.0"\ntransformations:\n  steps: []\n',
  destinations:    'version: "1.0"\ndestinations: {}\n',
  pipeline:        'version: "1.0"\npipeline:\n  name: my_job\n  from: ""\n  to: ""\n',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface YamlCodePanelProps {
  nodes:   Node<FlowNodeData>[]
  edges:   Edge[]
  meta:    { name: string; triggerType: 'manual' | 'schedule' | 'webhook'; cron?: string }
  onApply: (nodes: Node<FlowNodeData>[], edges: Edge[]) => void
  onClose: () => void
  /** 'job' = Job Builder (.hdr) ; 'workflow' = orchestrateur (défaut) */
  mode?:   'workflow' | 'job'
}

type SyncStatus = 'synced' | 'editing' | 'error'

// ── Skeleton generator ────────────────────────────────────────────────────────

function buildSkeleton(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  meta:  { name: string; triggerType: string; cron?: string }
): string {
  if (nodes.length === 0) {
    return [
      'version: "1.0"',
      'workflow:',
      `  name: "${meta.name || 'my_workflow'}"  # TODO: rename`,
      '  trigger:',
      '    type: manual  # manual | schedule | webhook',
      '    # cron: "0 8 * * *"  # uncomment for schedule',
      '  steps:',
      '    - name: "extract"',
      '      type: job',
      '      job: "./jobs/extract.yaml"  # TODO: set path',
      '    - name: "transform"',
      '      type: job',
      '      job: "./jobs/transform.yaml"  # TODO: set path',
      '      depends_on: ["extract"]',
      '    - name: "load"',
      '      type: job',
      '      job: "./jobs/load.yaml"  # TODO: set path',
      '      depends_on: ["transform"]',
      '    - name: "notify"',
      '      type: action',
      '      action: webhook',
      '      params:',
      '        url: ""  # TODO: set webhook URL',
      '      depends_on: ["load"]',
    ].join('\n')
  }

  try {
    const wf: WorkflowYAML = flowToWorkflow(
      nodes, edges,
      meta as { name: string; triggerType: 'manual' | 'schedule' | 'webhook'; cron?: string }
    )
    const lines: string[] = []
    lines.push(`version: "${wf.version}"`)
    lines.push('workflow:')
    lines.push(`  name: "${wf.workflow.name}"`)
    lines.push('  trigger:')
    lines.push(`    type: ${wf.workflow.trigger.type}`)
    if (wf.workflow.trigger.cron) lines.push(`    cron: "${wf.workflow.trigger.cron}"`)
    if (wf.workflow.steps.length === 0) { lines.push('  steps: []'); return lines.join('\n') }
    lines.push('  steps:')
    for (const step of wf.workflow.steps) {
      lines.push(`    - name: "${step.name}"`)
      lines.push(`      type: ${step.type}`)
      if (step.type === 'job') {
        const p = step.job ?? ''
        lines.push(`      job: "${p}"${!p ? '  # TODO: set job path' : ''}`)
      } else {
        if (step.action) lines.push(`      action: ${step.action}`)
        lines.push('      params:')
        const params = (step.params ?? {}) as Record<string, string>
        if (!Object.keys(params).length) lines.push('        # TODO: add parameters')
        else for (const [k, v] of Object.entries(params)) {
          const sv = String(v)
          lines.push(`        ${k}: "${sv}"${!sv ? '  # TODO' : ''}`)
        }
      }
      if (step.depends_on?.length)
        lines.push(`      depends_on: [${step.depends_on.map(d => `"${d}"`).join(', ')}]`)
      if (step.on_failure) lines.push(`      on_failure: ${step.on_failure}`)
      if (step.enabled === false) lines.push('      enabled: false')
    }
    return lines.join('\n')
  } catch {
    return buildSkeleton([], [], meta)
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

// ── IconBtn ────────────────────────────────────────────────────────────────────
import React from 'react'
function IconBtn({ title, onClick, active, children }: {
  title: string; onClick: () => void; active: boolean; children: React.ReactNode
}) {
  return (
    <button title={title} onClick={onClick} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      width: 24, height: 24, borderRadius: 4,
      background: active ? 'var(--primary-subtle)' : 'transparent',
      border: 'none', cursor: 'pointer',
      color: active ? 'var(--primary)' : 'var(--text-muted)', transition: 'all 0.15s',
    }}>
      {children}
    </button>
  )
}

function _hdrSkeleton(name: string): string {
  return `version: "1.0"\njob:\n  name: "${name || 'my_job'}"\n  sources:\n    input:\n      type: csv\n      connection:\n        file: ""\n      extract:\n        table: ""\n  transformations:\n    steps: []\n  destinations:\n    output:\n      type: csv\n      connection:\n        file: ""\n      load:\n        table: ""\n        mode: replace\n  pipeline:\n    name: "${name || 'my_job'}"\n    from: input\n    to: output`
}

export default function YamlCodePanel({ nodes, edges, meta, onApply, onClose, mode = 'workflow' }: YamlCodePanelProps) {
  const isJobMode = mode === 'job'

  // ── État onglets (mode job) ───────────────────────────────────────────────
  const [activeTab,  setActiveTab]  = useState<JobTab>('sources')
  const [sections,   setSections]   = useState<JobSectionYamls>(EMPTY_SECTIONS)
  const [tabErrors,  setTabErrors]  = useState<Partial<Record<JobTab, string>>>({})

  // ── État éditeur monolithique (mode workflow) ─────────────────────────────
  const [yamlText, setYamlText] = useState('')
  const [status,   setStatus]   = useState<SyncStatus>('synced')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [copied,   setCopied]   = useState(false)
  const [toast,    setToast]    = useState<string | null>(null)

  const userEditing = useRef(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  const toastRef    = useRef<ReturnType<typeof setTimeout>>()

  // ── Resize ────────────────────────────────────────────────────────────────
  const [panelWidth, setPanelWidth] = useState<number>(() => {
    try { return parseInt(localStorage.getItem('hydra-yaml-width') ?? '480') || 480 } catch { return 480 }
  })
  const resizing  = useRef(false)
  const resizeRef = useRef({ startX: 0, startW: 0 })

  const handleResizeDown = useCallback((e: ReactMouseEvent) => {
    e.preventDefault()
    resizing.current = true
    resizeRef.current = { startX: e.clientX, startW: panelWidth }

    const onMove = (ev: MouseEvent) => {
      if (!resizing.current) return
      const delta = resizeRef.current.startX - ev.clientX   // drag left = wider
      const w = Math.max(240, Math.min(960, resizeRef.current.startW + delta))
      setPanelWidth(w)
    }
    const onUp = () => {
      resizing.current = false
      try { localStorage.setItem('hydra-yaml-width', String(panelWidth)) } catch { /* noop */ }
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup',   onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup',   onUp)
  }, [panelWidth])

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    if (toastRef.current) clearTimeout(toastRef.current)
    toastRef.current = setTimeout(() => setToast(null), 2200)
  }, [])

  // ── Canvas → sections YAML (mode job) ───────────────────────────────────

  useEffect(() => {
    if (!isJobMode || userEditing.current) return
    if (nodes.length === 0) { setSections(EMPTY_SECTIONS); return }
    try {
      const model = flowToJobModel(nodes, edges, meta.name || 'my_job')
      setSections(jobModelToSectionYamls(model))
      setTabErrors({})
    } catch { /* garder les sections existantes */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, meta.name, isJobMode])

  // Init au montage (mode job)
  useEffect(() => {
    if (!isJobMode) return
    if (nodes.length === 0) { setSections(EMPTY_SECTIONS); return }
    try {
      const model = flowToJobModel(nodes, edges, meta.name || 'my_job')
      setSections(jobModelToSectionYamls(model))
    } catch { setSections(EMPTY_SECTIONS) }
  }, []) // eslint-disable-line

  // ── Onglet YAML → canvas (debounced 800ms, mode job) ─────────────────────

  const handleTabChange = useCallback((tab: JobTab, value: string) => {
    const next = { ...sections, [tab]: value }
    setSections(next)
    userEditing.current = true
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      try {
        const model = sectionYamlsToJobModel(next, meta.name || 'my_job')
        if (!model) throw new Error('Invalid structure')
        const { nodes: n, edges: e } = jobModelToFlow(model)
        onApply(n, e)
        setTabErrors(prev => { const p = { ...prev }; delete p[tab]; return p })
      } catch (err) {
        setTabErrors(prev => ({ ...prev, [tab]: (err as Error).message }))
      } finally { userEditing.current = false }
    }, 800)
  }, [sections, meta.name, onApply])

  // ── Canvas → YAML monolithique (mode workflow) ────────────────────────────

  const generateYaml = useCallback((): string => {
    try {
      if (isJobMode) return flowToHdr(nodes, edges, meta.name || 'my_job') || _hdrSkeleton(meta.name)
      return workflowToYAMLString(flowToWorkflow(nodes, edges, meta))
    } catch (e) { return `# Error: ${(e as Error).message}` }
  }, [nodes, edges, meta, isJobMode])

  useEffect(() => {
    if (isJobMode || userEditing.current) return
    setYamlText(generateYaml()); setStatus('synced'); setErrorMsg(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, meta.name, meta.triggerType, meta.cron])

  useEffect(() => { if (!isJobMode) setYamlText(generateYaml()) }, []) // eslint-disable-line

  // ── YAML monolithique → canvas (debounced 800ms, mode workflow) ──────────

  const handleChange = useCallback((value: string) => {
    setYamlText(value)
    setStatus('editing')
    userEditing.current = true
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      try {
        const wf = parseWorkflowYAML(value)
        if (!wf) throw new Error('Invalid YAML structure')
        const { nodes: n, edges: e } = workflowToFlow(wf)
        onApply(n as Node<FlowNodeData>[], e)
        setStatus('synced'); setErrorMsg(null)
      } catch (e) {
        setStatus('error'); setErrorMsg((e as Error).message)
      } finally { userEditing.current = false }
    }, 800)
  }, [onApply])

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleResync = useCallback(() => {
    userEditing.current = false
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (isJobMode) {
      const model = flowToJobModel(nodes, edges, meta.name || 'my_job')
      setSections(jobModelToSectionYamls(model))
      setTabErrors({})
    } else {
      setYamlText(generateYaml()); setStatus('synced'); setErrorMsg(null)
    }
  }, [isJobMode, nodes, edges, meta, generateYaml])

  const handleInitialize = useCallback(() => {
    if (isJobMode) {
      setSections(EMPTY_SECTIONS)
      setTabErrors({})
    } else {
      const sk = buildSkeleton(nodes, edges, meta)
      setYamlText(sk)
      handleChange(sk)
    }
  }, [isJobMode, nodes, edges, meta, handleChange])

  const handleCopy = useCallback(() => {
    const text = isJobMode ? sections[activeTab] : yamlText
    navigator.clipboard.writeText(text).catch(() => {})
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }, [isJobMode, sections, activeTab, yamlText])

  // ── Status ────────────────────────────────────────────────────────────────

  const statusColor = status === 'synced' ? 'var(--success)'
    : status === 'error' ? 'var(--error)' : 'var(--warning)'
  const statusLabel = status === 'synced' ? '● synced'
    : status === 'editing' ? '● editing…' : '● error'

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{
      width: panelWidth, display: 'flex', flexDirection: 'column',
      background: '#282c34',  /* oneDark background */
      borderLeft: '1px solid var(--bg-border)',
      position: 'relative', zIndex: 10, flexShrink: 0,
    }}>

      {/* ── Resize handle (pill élégant, cohérent avec Output panel) ── */}
      <div
        onMouseDown={handleResizeDown}
        title="Drag to resize"
        style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: 6,
          cursor: 'col-resize', zIndex: 20,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        onMouseEnter={e => {
          const pill = e.currentTarget.querySelector('div') as HTMLDivElement
          if (pill) pill.style.background = 'var(--primary)'
        }}
        onMouseLeave={e => {
          if (resizing.current) return
          const pill = e.currentTarget.querySelector('div') as HTMLDivElement
          if (pill) pill.style.background = 'var(--bg-border)'
        }}
      >
        <div style={{ width: 3, height: 32, borderRadius: 3, background: 'var(--bg-border)', transition: 'background 0.15s' }} />
      </div>

      {/* ── Header ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '0 10px', height: 40,
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--bg-border)', flexShrink: 0,
      }}>
        <Code2 size={13} style={{ color: isJobMode ? '#f59e0b' : 'var(--primary)' }} />
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'monospace', letterSpacing: '0.06em' }}>
          {isJobMode ? 'JOB' : 'YAML'}
        </span>
        {isJobMode && (
          <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(245,158,11,0.15)', color: '#f59e0b', marginLeft: 2, fontFamily: 'monospace' }}>
            multi-section
          </span>
        )}
        {!isJobMode && (
          <span style={{ marginLeft: 4, fontSize: 10, color: statusColor, fontFamily: 'monospace', transition: 'color 0.2s' }}>
            {statusLabel}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <IconBtn title="Resync from canvas" onClick={handleResync} active={false}><RefreshCw size={11} /></IconBtn>
        <IconBtn title={`Copy ${isJobMode ? activeTab : 'YAML'}`} onClick={handleCopy} active={copied}>
          {copied ? <Check size={11} /> : <Copy size={11} />}
        </IconBtn>
        <IconBtn title="Close" onClick={onClose} active={false}><X size={13} /></IconBtn>
      </div>

      {/* ── Onglets (mode job uniquement) ── */}
      {isJobMode && (
        <div style={{
          display: 'flex', gap: 0,
          background: 'var(--bg-card)',
          borderBottom: '1px solid var(--bg-border)',
          flexShrink: 0, overflowX: 'auto',
        }}>
          {JOB_TABS.map(tab => {
            const hasError = !!tabErrors[tab.key]
            const isActive = activeTab === tab.key
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: '7px 14px',
                  fontSize: 11,
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: isActive ? '2px solid var(--primary)' : '2px solid transparent',
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  whiteSpace: 'nowrap', transition: 'all 0.15s',
                }}>
                {hasError && <span style={{ color: 'var(--error)', marginRight: 4 }}>⚠</span>}
                {tab.label}
              </button>
            )
          })}
        </div>
      )}

      {/* ── Éditeur CodeMirror ── */}
      <div style={{ flex: 1, overflow: 'auto', position: 'relative', minHeight: 0 }}>
        <CodeMirror
          value={isJobMode ? (sections[activeTab] ?? '') : yamlText}
          height="100%"
          extensions={[yaml()]}
          theme={oneDark}
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            highlightActiveLine: true,
            autocompletion: true,
          }}
          onChange={(val) => {
            if (isJobMode) handleTabChange(activeTab, val)
            else handleChange(val)
          }}
          style={{ height: '100%', fontSize: 12 }}
        />
        {isJobMode && tabErrors[activeTab] && (
          <div style={{
            position: 'absolute', bottom: 8, left: 8, right: 8,
            background: 'var(--error)', color: '#fff', borderRadius: 6,
            padding: '6px 10px', fontSize: 11, zIndex: 10,
          }}>
            {tabErrors[activeTab]}
          </div>
        )}
      </div>

    </div>
  )
}
