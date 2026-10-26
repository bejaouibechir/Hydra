import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Globe, FolderCog } from 'lucide-react'

export interface AppSettings {
  autosave_enabled: boolean
  autosave_delay: number
  output_preview_rows: number
  /** Synchronisation automatique jobs ↔ disque, en secondes (0 = arrêt). */
  disk_sync_interval: number
}

const DEFAULTS: AppSettings = {
  autosave_enabled: true,
  autosave_delay: 3000,
  output_preview_rows: 10,
  disk_sync_interval: 5,
}

export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem('hydra-settings')
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {}
  return { ...DEFAULTS }
}

export function saveSettings(s: AppSettings) {
  localStorage.setItem('hydra-settings', JSON.stringify(s))
}

/**
 * Settings — deux onglets :
 *  - Global settings : préférences de Studio, gardées dans ce navigateur ;
 *  - Project settings : réglages du projet courant, écrits dans ses fichiers
 *    (ordre d'exécution : workflows/thread.yaml).
 */
export default function Settings() {
  const tab = (active: boolean): React.CSSProperties => ({
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8,
    fontSize: 13, fontWeight: 600, textDecoration: 'none',
    background: active ? 'var(--primary)' : 'transparent', color: active ? '#fff' : 'var(--text-muted)',
  })
  return (
    <div>
      <div data-testid="settings-tabs" style={{ display: 'inline-flex', gap: 4, padding: 3, marginBottom: 16,
        borderRadius: 10, background: 'var(--bg-hover)' }}>
        <NavLink to="/settings/global" style={({ isActive }) => tab(isActive)}>
          <Globe size={14} /> Global settings
        </NavLink>
        <NavLink to="/settings/project" style={({ isActive }) => tab(isActive)}>
          <FolderCog size={14} /> Project settings
        </NavLink>
      </div>
      <Outlet />
    </div>
  )
}

/** Onglet Global settings : préférences de l'éditeur (localStorage). */
export function GlobalSettings() {
  const [rows, setRows] = useState<number>(loadSettings().output_preview_rows)
  const [saved, setSaved] = useState(false)
  const [syncSec, setSyncSec] = useState<number>(loadSettings().disk_sync_interval)

  const commitSync = (v: number) => {
    const n = Math.max(0, Math.min(3600, Math.floor(v) || 0))
    setSyncSec(n)
    saveSettings({ ...loadSettings(), disk_sync_interval: n })
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  const commit = (v: number) => {
    const n = Math.max(1, Math.min(1000, Math.floor(v) || 1))
    setRows(n)
    saveSettings({ ...loadSettings(), output_preview_rows: n })
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Global settings</h2>
      <p className="text-slate-400 text-sm" style={{ marginBottom: 20 }}>
        Hydra Studio editor preferences, for every project. Kept in this browser only.
      </p>

      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
        Data viewer — number of output rows to display
      </label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <input
          type="number"
          min={1}
          max={1000}
          value={rows}
          onChange={e => setRows(Number(e.target.value))}
          onBlur={e => commit(Number(e.target.value))}
          style={{
            width: 100, padding: '6px 10px', borderRadius: 6,
            border: '1px solid var(--bg-border)', background: 'var(--bg-card)',
            color: 'var(--text-primary)', fontSize: 13,
          }}
        />
        <span className="text-slate-400 text-xs">
          rows (default: 10) — used when you right-click a destination and select “View data”.
        </span>
      </div>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, margin: '22px 0 6px' }}>
        Job files — automatic sync with the disk
      </label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <input
          type="number"
          min={0}
          max={3600}
          value={syncSec}
          aria-label="Disk sync interval in seconds"
          onChange={e => setSyncSec(Number(e.target.value))}
          onBlur={e => commitSync(Number(e.target.value))}
          style={{
            width: 100, padding: '6px 10px', borderRadius: 6,
            border: '1px solid var(--bg-border)', background: 'var(--bg-card)',
            color: 'var(--text-primary)', fontSize: 13,
          }}
        />
        <span className="text-slate-400 text-xs">
          seconds (default: 5, 0 = off) — every interval, the open job is compared with
          jobs/&lt;name&gt;/*.yaml and the latest change wins, in Studio or outside.
          Applies to editors opened after the change.
        </span>
      </div>
      {saved && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--primary)' }}>✓ Saved</div>
      )}
    </div>
  )
}
