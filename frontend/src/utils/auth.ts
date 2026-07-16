/**
 * 前端权限/角色工具函数。
 * 统一从 localStorage 读取 JWT 并解析 role。
 */

function getToken(): string | null {
  return localStorage.getItem('token')
}

function decodePayload(token: string): any | null {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}

export function getCurrentRole(): string | null {
  const token = getToken()
  if (!token) return null
  const payload = decodePayload(token)
  return payload?.role ?? null
}

export function isRootUser(): boolean {
  return getCurrentRole() === 'ROOT'
}

export function hasRole(role: string): boolean {
  return getCurrentRole() === role
}