import React from 'react'
import { usePermission } from '../../hooks/usePermission'
import type { UserRole } from '../../store/auth'

interface PermissionGuardProps {
  role?: UserRole
  minRole?: UserRole
  permission?: string
  fallback?: React.ReactNode
  children: React.ReactNode
}

const ROLE_HIERARCHY: Record<UserRole, number> = {
  ROOT: 3,
  ADMIN: 2,
  USER: 1,
}

export function PermissionGuard({
  role,
  minRole,
  permission,
  fallback = null,
  children,
}: PermissionGuardProps) {
  const { role: currentRole, permissions, hasRole, hasPermission } = usePermission()

  // Check exact role match
  if (role && !hasRole(role)) {
    return <>{fallback}</>
  }

  // Check minimum role level (hierarchical)
  if (minRole) {
    const currentLevel = ROLE_HIERARCHY[currentRole] ?? 0
    const requiredLevel = ROLE_HIERARCHY[minRole] ?? 0
    if (currentLevel < requiredLevel) {
      return <>{fallback}</>
    }
  }

  // Check specific permission
  if (permission && !hasPermission(permission)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}

export function AdminGuard({ children, fallback }: { children: React.ReactNode; fallback?: React.ReactNode }) {
  return (
    <PermissionGuard role="ROOT" fallback={fallback}>
      {children}
    </PermissionGuard>
  )
}

export function ManagerGuard({ children, fallback }: { children: React.ReactNode; fallback?: React.ReactNode }) {
  return (
    <PermissionGuard minRole="ADMIN" fallback={fallback}>
      {children}
    </PermissionGuard>
  )
}