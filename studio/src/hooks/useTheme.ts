import { useState, useEffect, useCallback } from 'react'
import { applyTheme, loadSavedTheme, THEMES, Theme } from '@/lib/themes'

export function useTheme() {
  const [themeId, setThemeId] = useState<string>(loadSavedTheme)

  // Appliquer le thème sauvegardé au montage
  useEffect(() => {
    applyTheme(themeId)
  }, [])

  const setTheme = useCallback((id: string) => {
    setThemeId(id)
    applyTheme(id)
  }, [])

  const currentTheme: Theme = THEMES.find(t => t.id === themeId) ?? THEMES[0]

  return { themeId, currentTheme, themes: THEMES, setTheme }
}
