import type { UserRole } from '../store/auth'

/**
 * 根据用户角色返回对应的默认工作空间路由。
 */
export function redirectByRole(role: UserRole): string {
  switch (role) {
    case 'ROOT':
      return '/platform'
    case 'ADMIN':
      return '/organization'
    case 'USER':
      return '/workspace'
    default:
      return '/login'
  }
}