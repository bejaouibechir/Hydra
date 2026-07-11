import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { StepResult } from '@/lib/api'
import { useRunDetail, isRunActive } from '@/hooks/useRunPolling'
import StatusBadge from '@/components/ui/StatusBadge'
import Spinner from '@/components/ui/Spinner'
import LiveBadge from '@/components/ui/LiveBadge'
import LogViewer from '@/components/ui/LogViewer'
import {
  ChevronLeft, CheckCircle2, XCircle, Clock,
  AlertTriangle, ChevronDown, ChevronRight, SkipForward,
} from 'lucide-react'
import clsx from 'clsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(s?: number) {
  if (s == null) return '—'
  return s < 60 ? `${s.toFixed(3)}s` : `${(s / 60).toFixed(2)}m`
}

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function stepStatus(s: StepResult): 'success' | 'failed' | 'skipped' | 'running' {
  if (s.skipped)  return 'skipped'
  if (s.success)  return 'success'
  return 'failed'
}

const STATUS_ICON = {
  success: <CheckCircle2 size={15} />,
  failed:  <XCircle size={15} />,
  skipped: <SkipForward size={15} />,
  running: <Clock size={15} className="animate-spin-slow" />,
}
const STATUS_COLOR = {
  success: 'var(--success)',
  failed:  'var(--error)',
  skipped: 'var(--text-muted)',
  running: 'var(--info)',
}
const STATUS_BORDER = {
  success: 'rgba(16,185,129,0.3)',
  failed:  'rgba(239,68,68,0.3)',
  skipped: 'var(--bg-border)',
  running: 'rgba(59,130,246,0.4)',
}

// ── Timeline bar ──────────────────────────────────────────────────────────────

function TimelineBar({ steps, totalDuration }: { steps: StepResult[]; totalDuration: number }) {
  if (steps.length === 0 || !totalDuration) return null
  return (
    <div className="rounded-xl p-4 mb-6" style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
      <p className="text-xs font-semibold mb-3" style={{ color: 'var(--text-muted)' }}>EXECUTION TIMELINE</p>
      <div className="space-y-1.5">
        {steps.map((step, i) => {
          const pct = totalDuration > 0 ? (step.duration / totalDuration) * 100 : 0
          const st  = stepStatus(step)
          const color = STATUS_COLOR[st]
          // Offset basé sur le début approximatif (somme des durées précédentes)
          const offset = steps.slice(0, i).reduce((acc, s) => acc + (s.duration ?? 0), 0)
          const offsetPct = totalDuration > 0 ? (offset / totalDuration) * 100 : 0

          return (
            <div key={step.step_name} className="flex items-center gap-2">
              <span className="text-xs font-mono w-28 shrink-0 truncate text-right"
                style={{ color: 'var(--text-secondary)' }}>
                {step.step_name}
              </span>
              <div className="flex-1 h-4 rounded relative" style={{ background: 'var(--bg-hover)' }}>
                <div
                  className="absolute top-0 h-full rounded"
                  style={{
                    left:    `${Math.min(offsetPct, 98)}%`,
                    width:   `${Math.max(pct, 0.5)}%`,
                    background: color,
                    opacity: st === 'skipped' ? 0.3 : 0.8,
                  }}
                />
              </div>
              <span className="text-xs font-mono w-14 shrink-0" style={{ color: 'var(--text-muted)' }}>
                {fmtDuration(step.duration)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── StepCard ─────────────────────────────────────────────────────────────────

function StepCard({ step, index, defaultOpen = false }: {
  step: StepResult; index: number; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen || Boolean(step.error))
  const st    = stepStatus(step)
  const color = STATUS_COLOR[st]

  return (
    <div className="rounded-xl overflow-hidden transition-all"
      style={{ border: `1px solid ${STATUS_BORDER[st]}` }}>
      {/* Header row */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:opacity-90"
        style={{ background: 'var(--bg-card)' }}
      >
        {/* Index */}
        <span className="text-xs font-mono px-1.5 py-0.5 rounded shrink-0"
          style={{ background: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
          #{index + 1}
        </span>

        {/* Icon */}
        <span style={{ color }}>{STATUS_ICON[st]}</span>

        {/* Name */}
        <span className="flex-1 font-medium text-sm text-left truncate" style={{ color: 'var(--text-primary)' }}>
          {step.step_name}
        </span>

        {/* Duration */}
        <span className="text-xs font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>
          {fmtDuration(step.duration)}
        </span>

        {/* Logs count */}
        {step.logs && step.logs.length > 0 && (
          <span className="text-xs px-1.5 py-0.5 rounded shrink-0"
            style={{ background: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
            {step.logs.length} lines
          </span>
        )}

        {/* Expand toggle */}
        {open ? <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />
               : <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />}
      </button>

      {/* Expanded content */}
      {open && (
        <div className="px-4 pb-4 pt-2 space-y-3" style={{ background: 'var(--bg-card)', borderTop: '1px solid var(--bg-border)' }}>
          {/* Skipped banner */}
          {step.skipped && (
            <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
              style={{ background: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
              <SkipForward size={12} /> Step skipped — upstream dependency failed.
            </div>
          )}

          {/* Error banner */}
          {step.error && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg text-xs"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: 'var(--error)' }}>
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span className="font-mono">{step.error}</span>
            </div>
          )}

          {/* Logs */}
          {step.logs && step.logs.length > 0
            ? <LogViewer lines={step.logs} title={step.step_name} maxHeight={240} />
            : <p className="text-xs italic" style={{ color: 'var(--text-muted)' }}>No logs captured for this step.</p>
          }
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const { data: run, isLoading } = useRunDetail(runId)

  if (isLoading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  if (!run)      return <p style={{ color: 'var(--error)' }}>Run not found.</p>

  const live           = isRunActive(run)
  const successCount   = run.steps.filter(s => s.success && !s.skipped).length
  const skippedCount   = run.steps.filter(s => s.skipped).length
  const totalDuration  = run.duration ?? run.steps.reduce((a, s) => a + (s.duration ?? 0), 0)
  // Ouvrir automatiquement le step qui a échoué
  const firstFailedIdx = run.steps.findIndex(s => !s.success && !s.skipped)

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
        <Link to="/runs" className="flex items-center gap-1 hover:opacity-70 transition-opacity">
          <ChevronLeft size={14} /> Runs
        </Link>
        <span>/</span>
        <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{run.workflow_name}</span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>#{run.run_id.slice(0, 8)}</span>
      </div>

      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">{run.workflow_name}</h1>
          <p className="text-xs mt-0.5 font-mono" style={{ color: 'var(--text-muted)' }}>{run.run_id}</p>
        </div>
        <div className="flex items-center gap-2">
          {live && <LiveBadge />}
          <StatusBadge status={run.status} />
        </div>
      </div>

      {/* Meta cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Started',  value: fmtDate(run.started_at) },
          { label: 'Finished', value: live ? '…' : fmtDate(run.finished_at) },
          { label: 'Duration', value: live ? <span className="flex items-center gap-1" style={{ color: 'var(--info)' }}><Clock size={11} className="animate-spin-slow" /> running</span> : fmtDuration(totalDuration) },
          { label: 'Steps',    value: `${successCount} ok${skippedCount ? ` · ${skippedCount} skip` : ''} / ${run.steps.length}` },
        ].map(({ label, value }) => (
          <div key={label} className="card !py-3">
            <p className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</p>
            <p className="text-sm font-medium font-mono" style={{ color: 'var(--text-primary)' }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Run-level error */}
      {run.error && !run.steps.some(s => s.error === run.error) && (
        <div className="rounded-xl px-4 py-3 mb-6 flex items-start gap-2"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)' }}>
          <AlertTriangle size={15} className="mt-0.5 shrink-0" style={{ color: 'var(--error)' }} />
          <div>
            <p className="text-xs font-semibold mb-0.5" style={{ color: 'var(--error)' }}>Run error</p>
            <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{run.error}</p>
          </div>
        </div>
      )}

      {/* Timeline */}
      {run.steps.length > 1 && (
        <TimelineBar steps={run.steps} totalDuration={totalDuration} />
      )}

      {/* Steps */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Steps ({run.steps.length})
        </h2>
        {live && (
          <span className="text-xs flex items-center gap-1" style={{ color: 'var(--info)' }}>
            <Clock size={11} className="animate-spin-slow" /> Polling every 2s
          </span>
        )}
      </div>

      {run.steps.length === 0
        ? <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {live
              ? <span className="flex items-center gap-2">
                  <Clock size={14} className="animate-spin-slow" style={{ color: 'var(--info)' }} /> Waiting for steps…
                </span>
              : 'No step data.'}
          </p>
        : <div className="space-y-2">
            {run.steps.map((step, i) => (
              <StepCard
                key={step.step_name + i}
                step={step}
                index={i}
                defaultOpen={i === firstFailedIdx}
              />
            ))}
          </div>}
    </div>
  )
}
