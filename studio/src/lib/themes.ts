export interface Theme { id: string; label: string; mode: 'dark' | 'light'; preview: string }

export const THEMES: Theme[] = [
  { id: 'dark',     label: 'Hydra Dark',  mode: 'dark',  preview: '#6366f1' },
  { id: 'midnight', label: 'Midnight',    mode: 'dark',  preview: '#8b5cf6' },
  { id: 'ocean',    label: 'Ocean',       mode: 'dark',  preview: '#06b6d4' },
  { id: 'light',    label: 'Hydra Light', mode: 'light', preview: '#4f46e5' },
]

export const DEFAULT_THEME = 'dark'

export const THEME_VARS: Record<string, Record<string, string>> = {
  dark: {
    '--bg-surface': '#0f0f18', '--bg-card': '#1a1a2e', '--bg-border': '#2d2d4e',
    '--bg-hover': '#252540', '--bg-input': '#16213e',
    '--text-primary': '#f1f5f9', '--text-secondary': '#94a3b8', '--text-muted': '#64748b',
    '--primary': '#6366f1', '--primary-hover': '#4f46e5', '--primary-subtle': 'rgba(99,102,241,0.15)',
    '--success': '#10b981', '--error': '#ef4444', '--warning': '#f59e0b', '--info': '#3b82f6',
    '--canvas-dot': 'rgba(255,255,255,0.35)',
  },
  midnight: {
    '--bg-surface': '#000000', '--bg-card': '#0d0d0d', '--bg-border': '#1f1f1f',
    '--bg-hover': '#141414', '--bg-input': '#080808',
    '--text-primary': '#f8fafc', '--text-secondary': '#a1a1aa', '--text-muted': '#71717a',
    '--primary': '#8b5cf6', '--primary-hover': '#7c3aed', '--primary-subtle': 'rgba(139,92,246,0.15)',
    '--success': '#10b981', '--error': '#ef4444', '--warning': '#f59e0b', '--info': '#3b82f6',
    '--canvas-dot': 'rgba(255,255,255,0.28)',
  },
  ocean: {
    '--bg-surface': '#020c18', '--bg-card': '#071428', '--bg-border': '#0e2540',
    '--bg-hover': '#0a1c35', '--bg-input': '#040e1e',
    '--text-primary': '#e0f7fa', '--text-secondary': '#7ecfd8', '--text-muted': '#4a9ba8',
    '--primary': '#06b6d4', '--primary-hover': '#0891b2', '--primary-subtle': 'rgba(6,182,212,0.15)',
    '--success': '#10b981', '--error': '#ef4444', '--warning': '#f59e0b', '--info': '#22d3ee',
    '--canvas-dot': 'rgba(14,200,220,0.42)',
  },
  light: {
    '--bg-surface': '#f8fafc', '--bg-card': '#ffffff', '--bg-border': '#e2e8f0',
    '--bg-hover': '#f1f5f9', '--bg-input': '#f8fafc',
    '--text-primary': '#0f172a', '--text-secondary': '#475569', '--text-muted': '#94a3b8',
    '--primary': '#4f46e5', '--primary-hover': '#4338ca', '--primary-subtle': 'rgba(79,70,229,0.10)',
    '--success': '#059669', '--error': '#dc2626', '--warning': '#d97706', '--info': '#2563eb',
    '--canvas-dot': 'rgba(0,0,0,0.45)',
  },
}

export function applyTheme(themeId: string) {
  const vars = THEME_VARS[themeId] ?? THEME_VARS['dark']
  const root = document.documentElement
  root.setAttribute('data-theme', themeId)
  Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v))
  localStorage.setItem('hydra-theme', themeId)
}

export function loadSavedTheme(): string {
  return localStorage.getItem('hydra-theme') ?? DEFAULT_THEME
}
