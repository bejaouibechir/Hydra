import { useLocation } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import ThemeSwitcher from '@/components/ui/ThemeSwitcher'
import NotificationDropdown from '@/components/ui/NotificationDropdown'

const TITLES: Record<string, string> = {
  '/overview':  'Overview',
  '/projects':  'Projects',
  '/runs':      'Runs',
  '/templates': 'Templates',
  '/insights':  'Insights',
  '/settings':  'Settings',
  '/help':      'Help',
}

export default function Topbar() {
  const { pathname } = useLocation()
  const title = Object.entries(TITLES).find(([k]) => pathname.startsWith(k))?.[1] ?? 'Hydra Studio'

  const { data: health, isError } = useQuery({
    queryKey: ['health'],
    queryFn:  api.health,
    refetchInterval: 5_000,
    retry: 0,
  })

  // Build exécuté par cet onglet vs build servi par `hdrctl serve` : s'ils
  // diffèrent, l'onglet affiche un ancien Studio (cache, onglet resté ouvert
  // pendant une mise à jour) → proposer de recharger.
  const runningBuild = (document.querySelector('script[type="module"][src*="/assets/index-"]') as HTMLScriptElement | null)
    ?.src.split('/assets/')[1] ?? ''
  const staleStudio = !!runningBuild && !!health?.studio_build && health.studio_build !== runningBuild

  const apiOnline = !!health && !isError
  const statusColor = isError ? 'var(--error)' : health ? 'var(--success)' : 'var(--text-muted)'
  const statusLabel = isError ? 'API offline' : health ? 'API online' : '…'

  return (
    <header
      className="h-14 flex items-center justify-between px-5 shrink-0 border-b"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--bg-border)' }}
    >
      <h1 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h1>

      <div className="flex items-center gap-2">
        {staleStudio && (
          <button type="button" data-testid="studio-update"
            onClick={() => window.location.reload()}
            title="This tab runs an older Hydra Studio than the one served by hdrctl serve"
            style={{
              fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
              border: '1px solid var(--warning)', background: 'var(--warning)', color: '#1a1a1a',
            }}>
            New Studio version — reload
          </button>
        )}
        {/* API status */}
        <div className="flex items-center gap-1.5 text-xs mr-1">
          <Activity size={13} style={{ color: statusColor }} />
          <span style={{ color: statusColor }}>{statusLabel}</span>
        </div>

        {/* Theme switcher */}
        <ThemeSwitcher />

        <NotificationDropdown />

        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white"
          style={{ background: 'var(--primary)' }}
        >
          H
        </div>
      </div>
    </header>
  )
}

