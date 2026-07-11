/**
 * pages/Insights.tsx
 * Statistiques agrégées sur les runs — calculées côté client depuis l'API runs.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export default function Insights() {
  const runsQ = useQuery({ queryKey: ['runs'], queryFn: () => api.runs.list() })

  const runs = runsQ.data ?? []
  const total   = runs.length
  const success = runs.filter(r => r.status === 'success').length
  const failed  = runs.filter(r => r.status === 'failed').length
  const running = runs.filter(r => r.status === 'running').length

  const avgDuration = runs.filter(r => r.duration != null).length > 0
    ? (runs.reduce((s, r) => s + (r.duration ?? 0), 0) / runs.filter(r => r.duration != null).length).toFixed(1)
    : '—'

  return (
    <div>
      <h1 className="text-xl font-bold mb-6" style={{ color: 'var(--text-primary)' }}>Insights</h1>
      {runsQ.isPending && <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Chargement…</p>}
      {runsQ.isError  && <p className="text-sm" style={{ color: 'var(--error)' }}>Erreur : {(runsQ.error as Error).message}</p>}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-8">
        {[
          { label: 'Total runs',    value: total   },
          { label: '✓ Succès',      value: success },
          { label: '✗ Échecs',      value: failed  },
          { label: '⟳ En cours',   value: running },
        ].map(({ label, value }) => (
          <div key={label} className="card p-4">
            <p className="text-2xl font-bold" style={{ color: 'var(--primary)' }}>{value}</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
          </div>
        ))}
      </div>
      <div className="card p-4">
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Durée moyenne : <strong style={{ color: 'var(--text-primary)' }}>{avgDuration} s</strong>
        </p>
      </div>
    </div>
  )
}
