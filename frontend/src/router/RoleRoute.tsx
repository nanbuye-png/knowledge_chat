import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore, type UserRole } from '../store/auth'

interface RoleRouteProps {
  allowedRoles: UserRole[]
  children: React.ReactNode
}

/**
 * 基于角色的页面访问控制组件。
 * 如果用户未登录则重定向到 /login；
 * 如果用户角色不在允许列表中则返回 403。
 */
export default function RoleRoute({ allowedRoles, children }: RoleRouteProps) {
  const token = localStorage.getItem('token')
  const userState = useAuthStore.getState().userState

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (!userState || !allowedRoles.includes(userState.role)) {
    return <Navigate to="/403" replace />
  }

  return <>{children}</>
}