import { createContext, useContext } from 'react'
import { Theme, THEMES } from '@/lib/themes'

export interface ThemeContextValue {
  themeId: string
  currentTheme: Theme
  themes: Theme[]
  setTheme: (id: string) => void
}

export const ThemeContext = createContext<ThemeContextValue>({
  themeId: 'dark',
  currentTheme: THEMES[0],
  themes: THEMES,
  setTheme: () => {},
})

export const useThemeContext = () => useContext(ThemeContext)
