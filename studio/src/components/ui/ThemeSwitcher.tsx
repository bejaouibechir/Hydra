import { useState, useRef, useEffect } from 'react'
import { Palette, Check, Sun, Moon } from 'lucide-react'
import { useThemeContext } from '@/hooks/useThemeContext'
import clsx from 'clsx'

export default function ThemeSwitcher() {
  const { themeId, themes, setTheme } = useThemeContext()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Fermer au clic extérieur
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const current = themes.find(t => t.id === themeId)

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="btn-ghost p-2 !gap-0"
        title="Change theme"
      >
        {current?.mode === 'light' ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {open && (
        <div className="absolute right-0 top-10 z-50 w-52 rounded-xl border shadow-2xl overflow-hidden"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--bg-border)' }}>
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--bg-border)' }}>
            <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
              <Palette size={12} className="inline mr-1" />Theme
            </p>
          </div>
          <div className="p-1.5 space-y-0.5">
            {themes.map(theme => (
              <button
                key={theme.id}
                onClick={() => { setTheme(theme.id); setOpen(false) }}
                className={clsx(
                  'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  themeId === theme.id
                    ? 'font-medium'
                    : 'opacity-70 hover:opacity-100'
                )}
                style={{
                  background: themeId === theme.id ? 'var(--primary-subtle)' : 'transparent',
                  color: themeId === theme.id ? 'var(--primary)' : 'var(--text-secondary)',
                }}
              >
                {/* Colour swatch */}
                <span
                  className="w-4 h-4 rounded-full shrink-0 ring-2 ring-offset-1"
                  style={{
                    background: theme.preview,
                    boxShadow: themeId === theme.id ? `0 0 0 2px ${theme.preview}` : 'none',
                  }}
                />
                <span className="flex-1 text-left">{theme.label}</span>
                <span className="text-xs opacity-60">{theme.mode}</span>
                {themeId === theme.id && <Check size={13} />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
