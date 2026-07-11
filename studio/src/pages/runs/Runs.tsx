import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, Run } from '@/lib/api'
import { useRunsList, isRunActive } from '@/hooks/useRunPolling'
import StatusBadge from '@/components/ui/StatusBadge'
import Spinner from '@/components/ui/Spinner'
import EmptyState from '@/components/ui/EmptyState'
import LiveBadge from '@/components/ui/LiveBadge'
import { Play, Clock, Filter, RotateCcw } from 'lucide-react'
import clsx from 'clsx'

type StatusFilter = 'all' | Run['status']

const FILTERS: { label: string; value: StatusFilter }[] = [
  { label: 'All',     value: 'all' },
  { label: 'Running', value: 'running' },
  { label: 'Success', value: 'success' },
  { label: 'Failed',  value: 'failed' },
  { label: 'Pending', value: 'pending' },
]

function fmtDuration(s?: number) {
  if (s == null) return '—'
  return s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`
}

function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function RunAgainButton({ run }: { run: Run }) {
  const qc = useQueryClient()
  const mut = useMutation({
    mutationFn: () => {
      if (!run.workflow_path) throw new Error('workflow_path unavailable')
      return api.runs.start({ workflow_path: run.workflow_path })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })

  // Désactivé si pas de path connu (vieux runs sans le champ) ou run actif
  const disabled = mut.isPending || isRunActive(run) || !run.workflow_path

  return (
    <button
      onClick={e => { e.preventDefault(); mut.mutate() }}
      disabled={disabled}
      className="btn-ghost text-xs !px-2 !py-1 !gap-1"
      title={run.workflow_path ? 'Run again' : 'workflow_path unavailable'}
      style={{ color: disabled ? 'var(--bg-border)' : 'var(--text-muted)' }}
    >
      {mut.isPending ? <Spinner size="sm" /> : <RotateCcw size={12} />}
    </button>
  )
}

export default function Runs() {
  const [filter, setFilter] = useState<StatusFilter>('all')
  const { data, isLoading } = useRunsList()

  const hasLive = (data ?? []).some(r => isRunActive(r))
  const runs    = (data ?? []).filter(r => filter === 'all' || r.status === filter)

  const counts = {
    running: data?.filter(r => r.status === 'running').length ?? 0,
    success: data?.filter(r => r.status === 'success').length ?? 0,
    failed:  data?.filter(r => r.status === 'failed').length ?? 0,
    pending: data?.filter(r => r.status === 'pending').length ?? 0,
  }

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center gap-3">
          <h1 className="page-title">Runs</h1>
          {hasLive && <LiveBadge />}
        </div>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {data?.length ?? 0} total · {counts.running} running · {counts.success} success · {counts.failed} failed
        </p>
      </div>

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 mb-5 p-1 rounded-xl w-fit"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}>
        <Filter size={13} className="ml-2 shrink-0" style={{ color: 'var(--text-muted)' }} />
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{
              background: filter === f.value ? 'var(--primary)' : 'transparent',
              color:      filter === f.value ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {f.label}
            {f.value !== 'all' && data && counts[f.value as keyof typeof counts] > 0 && (
              <span className="ml-1 opacity-70">({counts[f.value as keyof typeof counts]})</span>
            )}
          </button>
        ))}
      </div>

      {isLoading
        ? <div className="flex justify-center py-20"><Spinner size="lg" /></div>
        : runs.length === 0
          ? <EmptyState
              icon={Play}
              title="No runs"
              description={filter === 'all' ? 'Execute a workflow to see runs here.' : `No ${filter} runs.`}
            />
          : (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--bg-border)' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--bg-border)', background: 'var(--bg-card)' }}>
                    {['Workflow', 'Status', 'Steps', 'Started', 'Duration', ''].map(h => (
                      <th key={h} className="px-4 py-2.5 text-left text-xs font-medium"
                        style={{ color: 'var(--text-muted)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run, i) => (
                    <tr
                      key={run.run_id}
                      style={{
                        borderBottom: i < runs.length - 1 ? '1px solid var(--bg-border)' : 'none',
                        background:   isRunActive(run) ? 'var(--primary-subtle)' : 'var(--bg-card)',
                      }}
                      className="hover:opacity-90 transition-all"
                    >
                      <td className="px-4 py-3 font-medium">
                        <Link
                          to={`/runs/${run.run_id}`}
                          className="hover:underline"
                          style={{ color: 'var(--primary)' }}
                        >
                          {run.workflow_name}
                        </Link>
                        <p className="text-xs mt-0.5 font-mono" style={{ color: 'var(--text-muted)' }}>
                          #{run.run_id.slice(0, 8)}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={run.status} />
                          {isRunActive(run) && <LiveBadge label="live" />}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {run.steps.length > 0
                          ? `${run.steps.filter(s => s.success).length}/${run.steps.length}`
                          : '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {fmtDate(run.started_at)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {run.status === 'running' || run.status === 'pending'
                          ? <span className="flex items-center gap-1.5" style={{ color: 'var(--info)' }}>
                              <Clock size={11} className="animate-spin-slow" />
                              {run.status}
                            </span>
                          : fmtDuration(run.duration)}
                      </td>
                      <td className="px-2 py-3">
                        <RunAgainButton run={run} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
    </div>
  )
}
