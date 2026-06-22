import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ThemeState } from '../types'

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'light',
      toggleTheme: () =>
        set((state) => ({
          theme: state.theme === 'light' ? 'dark' : 'light',
        })),
    }),
    {
      name: 'theme-storage',
    }
  )
)

// Apply theme on initialization
const savedTheme = localStorage.getItem('theme-storage')
if (savedTheme) {
  try {
    const parsed = JSON.parse(savedTheme)
    if (parsed.state?.theme === 'dark') {
      document.documentElement.classList.add('dark')
    }
  } catch {}
}