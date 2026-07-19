import { create } from 'zustand'
import * as authApi from '../api/auth'
import type { UserInfo } from '../api/auth'

export type UserRole = 'ROOT' | 'ADMIN' | 'USER'

export interface UserState {
  id: number
  username: string
  role: UserRole
  permissions: string[]
  isSystemAccount?: boolean
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  userState: UserState | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, email?: string | null) => Promise<void>
  logout: () => void
  fetchUser: () => Promise<void>
}

function getRole(user: UserInfo): UserRole {
  if (!user.role) return 'USER'
  const upper = user.role.toUpperCase()
  if (upper === 'ROOT') return 'ROOT'
  if (upper === 'ADMIN') return 'ADMIN'
  return 'USER'
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('token'),
  user: null,
  userState: null,
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
    set({ token: null, user: null, userState: null, isAuthenticated: false })
  },

  fetchUser: async () => {
    try {
      const user = await authApi.getMe()
      const role = getRole(user)
      const userState: UserState = {
        id: user.id,
        username: user.username,
        role,
        permissions: [],
        isSystemAccount: user.is_system_account ?? false,
      }
      set({ user, userState, isAuthenticated: true })
    } catch {
      get().logout()
    }
  },
}))