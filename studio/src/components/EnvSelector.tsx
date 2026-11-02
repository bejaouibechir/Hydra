/**
 * EnvSelector — choix de l'environnement actif du projet (page du projet,
 * en-tête de l'éditeur). Liste les environnements globaux (Global settings ›
 * Environments) et ceux du projet (environments/<env>.yaml). « default » :
 * aucun environnement. Les runs lancés depuis Studio l'utilisent.
 */
import { useQuery } from '@tanstack/react-query'
import { Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { useActiveEnv } from '@/lib/activeEnv'

interface Props { projectId?: string; compact?: boolean }

export default function EnvSelector({ projectId, compact = false }: Props) {
  const [env, setEnv] = useActiveEnv(projectId)
  const names = useQuery({
    queryKey: ['env-names', projectId ?? ''],
    queryFn: () => api.globalEnv.names(projectId),
    staleTime: 10_000,
  })
  const list = names.data ?? []
  const known = list.some(n => n.name === env)
  const current = list.find(n => n.name === env)
  const title = !env
    ? 'No environment: only the common global variables, the project .env and the default parameter values'
    : current
      ? `${env}: ${current.global_vars} global variable(s), ${current.params} parameter value(s), ${current.secrets} secret(s)`
      : `${env} is not defined any more`
  return (
    <label data-testid="env-selector" title={title}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
      <Layers size={14} />
      {!compact && <span style={{ fontWeight: 600 }}>Environment</span>}
      <select aria-label="Active environment" value={env} onChange={e => setEnv(e.target.value)}
        style={{ background: 'var(--bg-input)', border: `1px solid ${env ? 'var(--primary)' : 'var(--bg-border)'}`,
          borderRadius: 8, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 12, minWidth: 130, cursor: 'pointer' }}>
        <option value="">default (no environment)</option>
        {list.map(n => <option key={n.name} value={n.name}>{n.name}</option>)}
        {env && !known && <option value={env}>{env} (missing)</option>}
      </select>
      {!compact && (
        <Link to="/settings/global#environments" style={{ fontSize: 11, color: 'var(--primary)' }}>Manage</Link>
      )}
    </label>
  )
}
