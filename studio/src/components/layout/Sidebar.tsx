import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Play, LayoutTemplate,
  BarChart2, Settings, HelpCircle, Plus, Search, ChevronLeft,
} from 'lucide-react'
import HydraLogo from '@/images/Hydra.png'
import { useState } from 'react'
import clsx from 'clsx'

const NAV = [
  { to: '/overview',   icon: LayoutDashboard, label: 'Overview' },
  { to: '/runs',       icon: Play,            label: 'Runs' },
  { to: '/templates',  icon: LayoutTemplate,  label: 'Templates' },
  { to: '/insights',   icon: BarChart2,       label: 'Insights' },
]
const NAV_BOTTOM = [
  { to: '/settings',   icon: Settings,        label: 'Settings' },
  { to: '/help',       icon: HelpCircle,      label: 'Help' },
]

const STORAGE_KEY = 'hydra-sidebar-collapsed'

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem(STORAGE_KEY) === 'true' } catch { return false }
  })
  const navigate = useNavigate()

  const toggle = () => setCollapsed(v => {
    const next = !v
    try { localStorage.setItem(STORAGE_KEY, String(next)) } catch {}
    return next
  })

  return (
    <aside
      className={clsx(
        'flex flex-col h-full shrink-0',
        collapsed ? 'w-14' : 'w-52'
      )}
      style={{
        background: 'var(--bg-card)',
        borderRight: '1px solid var(--bg-border)',
        transition: 'width 0.2s ease',
      }}
    >
      {/* Logo + toggle */}
      <div className="flex items-center justify-between p-3 h-14"
        style={{ borderBottom: '1px solid var(--bg-border)' }}>
        <div className={clsx('flex items-center gap-2', collapsed && 'mx-auto')}>
          <img
            src={HydraLogo}
            alt="Hydra"
            className="shrink-0"
            style={{ width: 28, height: 28, objectFit: 'contain', borderRadius: 6 }}
          />
          {!collapsed && (
            <span className="font-bold text-sm tracking-wide" style={{ color: 'var(--text-primary)', letterSpacing: '0.08em' }}>
              HYDRA
            </span>
          )}
        </div>
        {!collapsed && (
          <div className="flex items-center gap-1">
            <button onClick={() => navigate('/overview')} className="btn-ghost p-1.5 !gap-0" title="New project">
              <Plus size={15} />
            </button>
            <button className="btn-ghost p-1.5 !gap-0" title="Search">
              <Search size={15} />
            </button>
            <button onClick={toggle} className="btn-ghost p-1.5 !gap-0" title="Collapse sidebar">
              <ChevronLeft size={15} />
            </button>
          </div>
        )}
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-2 space-y-0.5 px-2 overflow-y-auto">
        {collapsed && (
          <button
            onClick={toggle}
            title="Expand sidebar"
            className="btn-ghost w-full justify-center !px-2 !py-2 mb-1"
            style={{ color: 'var(--text-muted)' }}
          >
            <ChevronLeft size={15} className="rotate-180" />
          </button>
        )}
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} title={collapsed ? label : undefined}
            className={clsx(
              'flex items-center gap-3 px-2 py-2 rounded-lg text-sm transition-colors duration-100',
              collapsed && 'justify-center'
            )}
            style={({ isActive }) => isActive
              ? { background: 'var(--primary-subtle)', color: 'var(--primary)', fontWeight: 500 }
              : { color: 'var(--text-secondary)' }
            }
          >
            <Icon size={17} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="py-2 space-y-0.5 px-2" style={{ borderTop: '1px solid var(--bg-border)' }}>
        {NAV_BOTTOM.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} title={collapsed ? label : undefined}
            className={clsx(
              'flex items-center gap-3 px-2 py-2 rounded-lg text-sm transition-colors duration-100',
              collapsed && 'justify-center'
            )}
            style={({ isActive }) => isActive
              ? { background: 'var(--primary-subtle)', color: 'var(--primary)', fontWeight: 500 }
              : { color: 'var(--text-secondary)' }
            }
          >
            <Icon size={17} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </div>
    </aside>
  )
}

