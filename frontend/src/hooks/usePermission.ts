import { useMemo } from 'react'
import { useAuthStore, type UserRole } from '../store/auth'

export function usePermission() {
  const userState = useAuthStore((s) => s.userState)

  return useMemo(() => {
    const role: UserRole = userState?.role ?? 'USER'
    const permissions: string[] = userState?.permissions ?? []

    return {
      role,
      permissions,

      hasRole: (r: UserRole) => role === r,

      hasPermission: (perm: string) => permissions.includes(perm),

      isAdmin: () => role === 'ADMIN' || role === 'ROOT',

      isRoot: () => role === 'ROOT',

      isUser: () => role === 'USER',

      canManage: () => role === 'ROOT' || role === 'ADMIN',

      canAccessAdmin: () => role === 'ROOT',
    }
  }, [userState])
}