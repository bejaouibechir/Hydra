import { Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState, useCallback } from 'react'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import { useQuery } from '@tanstack/react-query'
import { useRunsList } from '@/hooks/useRunPolling'
import { useNotifications } from '@/contexts/NotificationContext'
import { api, type Run, type Workflow } from '@/lib/api'

interface Toast { id: string; type: 'success' | 'error'; title: string; message: string; link?: string }

/** Surveille les transitions de statut des runs, pousse des notifications
 *  ET affiche des toasts visibles sur toutes les vues (éditeur compris).
 *  Le nom du JOB en échec est résolu (jamais son identifiant interne),
 *  et le double-clic mène directement au job dans l'éditeur. */
function RunNotifier() {
  const { data: runs } = useRunsList()
  const { add } = useNotifications()
  const navigate = useNavigate()
  const prevRef = useRef<Map<string, Run['status']>>(new Map())
  const [toasts, setToasts] = useState<Toast[]>([])

  // Tous les workflows (tous projets) — pour résoudre chemin → id + noms de jobs
  const wfsQ = useQuery({ queryKey: ['workflows-all'], queryFn: () => api.workflows.list(), staleTime: 30_000 })

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const pushToast = useCallback((t: Toast) => {
    setToasts(prev => [...prev.slice(-2), t])
    setTimeout(() => dismissToast(t.id), 9000)
  }, [dismissToast])

  // Premier snapshot : on mémorise l'existant sans notifier (historique)
  const initializedRef = useRef(false)

  useEffect(() => {
    if (!runs) return
    const prev = prevRef.current
    const norm = (p?: string) => (p ?? '').replace(/\\/g, '/')

    if (!initializedRef.current) {
      for (const run of runs) prev.set(run.run_id, run.status)
      initializedRef.current = true
      return
    }

    for (const run of runs) {
      const was = prev.get(run.run_id)
      const isTerminal = run.status === 'success' || run.status === 'failed'
      // Notifier si : transition observée OU run nouveau déjà terminé
      // (les jobs rapides finissent entre deux sondages de la liste)
      const shouldNotify = isTerminal && (was ? was !== run.status : true)
      if (shouldNotify) {
        // Résolution : run → workflow (par chemin) → nom lisible du job en échec
        const wf = (wfsQ.data ?? []).find((w: Workflow) =>
          norm(w.path) === norm(run.workflow_path) && run.workflow_path)
        const failStep = run.steps?.find(s => !s.success && !s.skipped)?.step_name
        const jobNames = (wf?.layout?.job_names ?? {}) as Record<string, string>
        const friendly = failStep ? (jobNames[failStep] ?? failStep) : undefined
        const link = wf
          ? `/workflows/${wf.id}?projectId=${wf.project_id}${failStep ? `&jobId=${encodeURIComponent(failStep)}` : ''}`
          : `/runs/${run.run_id}`

        if (run.status === 'success') {
          const msg = `${run.workflow_name} a réussi`
          add('success', 'Run terminé', msg, wf ? `/workflows/${wf.id}?projectId=${wf.project_id}` : `/runs/${run.run_id}`)
          pushToast({ id: run.run_id + '-s', type: 'success', title: 'Run terminé', message: msg, link: wf ? `/workflows/${wf.id}?projectId=${wf.project_id}` : `/runs/${run.run_id}` })
        } else {
          const msg = friendly
            ? `${run.workflow_name} : le job « ${friendly} » a échoué — ${run.error ?? 'erreur inconnue'}`
            : `${run.workflow_name} : ${run.error ?? 'erreur inconnue'}`
          add('error', 'Run échoué', msg, link)
          pushToast({ id: run.run_id + '-f', type: 'error', title: 'Run échoué', message: msg, link })
        }
      }
      prev.set(run.run_id, run.status)
    }
    prevRef.current = prev
  }, [runs, add, wfsQ.data, pushToast])

  if (toasts.length === 0) return null
  return (
    <div style={{
      position: 'fixed', bottom: 18, right: 18, zIndex: 200,
      display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 380,
    }}>
      {toasts.map(t => (
        <div key={t.id}
          title="Double-clic : ouvrir le job concerné"
          onDoubleClick={() => { dismissToast(t.id); navigate(t.link ?? '/runs') }}
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer',
            padding: '10px 12px', borderRadius: 10,
            background: 'var(--bg-card)', boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            border: `1px solid ${t.type === 'error' ? 'rgba(239,68,68,0.5)' : 'rgba(34,197,94,0.5)'}`,
          }}>
          <div style={{
            width: 8, height: 8, borderRadius: 4, marginTop: 5, flexShrink: 0,
            background: t.type === 'error' ? 'var(--error)' : 'var(--success)',
          }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{t.title}</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.4 }}>{t.message}</div>
          </div>
          <button onClick={e => { e.stopPropagation(); dismissToast(t.id) }}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12, padding: 2, flexShrink: 0 }}>
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}

export default function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <RunNotifier />
    </div>
  )
}
