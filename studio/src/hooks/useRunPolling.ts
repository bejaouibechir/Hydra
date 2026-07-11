/**
 * useRunPolling — TanStack Query avec polling conditionnel.
 * - Active (2s) si status ∈ {pending, running}
 * - Désactive dès que status ∈ {success, failed}
 * - Expose isLive pour afficher un badge animé
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, Run } from '@/lib/api'

const TERMINAL = new Set(['success', 'failed'])

/** Intervalle de refetch conditionnel */
function interval(data: Run | undefined): number | false {
  if (!data) return 2_000                          // pas encore chargé → poll
  return TERMINAL.has(data.status) ? false : 2_000 // terminal → stop
}

/** Hook pour un run individuel */
export function useRunDetail(runId: string | undefined) {
  return useQuery({
    queryKey: ['run', runId],
    queryFn:  () => api.runs.logs(runId!),
    enabled:  Boolean(runId),
    refetchInterval: (q) => interval(q.state.data),
    staleTime: 0,
  })
}

/**
 * Hook pour la liste des runs.
 * Poll à 5s si au moins un run est actif, sinon 30s.
 */
export function useRunsList(workflowName?: string) {
  return useQuery({
    queryKey: ['runs', workflowName ?? ''],
    queryFn:  () => api.runs.list(workflowName),
    refetchInterval: (q) => {
      const runs = q.state.data as Run[] | undefined
      if (!runs) return 5_000
      const hasActive = runs.some(r => !TERMINAL.has(r.status))
      return hasActive ? 2_000 : 10_000
    },
    staleTime: 0,
  })
}

/** true si le run est en cours d'exécution */
export function isRunActive(run: Run | undefined): boolean {
  return Boolean(run && !TERMINAL.has(run.status))
}
