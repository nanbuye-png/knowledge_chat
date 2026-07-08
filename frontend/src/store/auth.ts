import { create } from 'zustand'
import * as authApi from '../api/auth'
import type { UserInfo } from '../api/auth'

interface AuthState {
  token: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, email?: string | null) => Promise<void>
  logout: () => void
  fetchUser: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('token'),
  user: null,
  isAuthenticated: !!localStorage.getItem('token'),

  login: async (username: string, password: string) => {
    const resp = await authApi.login({ username, password })
    localStorage.setItem('token', resp.access_token)
    set({ token: resp.access_token, isAuthenticated: true })
  },

  register: async (username: string, password: string, email?: string | null) => {
    await authApi.register({ username, password, email })
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ token: null, user: null, isAuthenticated: false })
  },

  fetchUser: async () => {
    try {
      const user = await authApi.getMe()
      set({ user, isAuthenticated: true })
    } catch {
      // Token invalid or expired
      get().logout()
    }
  },
}))