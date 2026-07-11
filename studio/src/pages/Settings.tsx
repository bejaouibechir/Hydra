import { useState } from 'react'

export interface AppSettings {
  autosave_enabled: boolean
  autosave_delay: number
  output_preview_rows: number
}

const DEFAULTS: AppSettings = {
  autosave_enabled: true,
  autosave_delay: 3000,
  output_preview_rows: 10,
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

export default function Settings() {
  const [rows, setRows] = useState<number>(loadSettings().output_preview_rows)
  const [saved, setSaved] = useState(false)

  const commit = (v: number) => {
    const n = Math.max(1, Math.min(1000, Math.floor(v) || 1))
    setRows(n)
    saveSettings({ ...loadSettings(), output_preview_rows: n })
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Settings</h2>
      <p className="text-slate-400 text-sm" style={{ marginBottom: 20 }}>
        Préférences de l\'éditeur Hydra Studio.
      </p>

      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
        Visionneuse — nombre de lignes de sortie à afficher
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
          lignes (défaut : 10) — appliqué au clic droit « View data » sur une destination.
        </span>
      </div>
      {saved && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--primary)' }}>✓ Enregistré</div>
      )}
    </div>
  )
}
