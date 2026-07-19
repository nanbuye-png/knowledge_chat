import { Navigate } from 'react-router-dom'
import EnterpriseLayout from '../../layout/EnterpriseLayout'
import { useAuthStore } from '../../store/auth'
import type { UserRole } from '../../store/auth'

interface ManagerRouteProps {
  children: React.ReactNode
  allowedRoles?: UserRole[]
}

/**
 * ManagerRoute — 允许 ROOT 和 ADMIN 访问，USER 跳转到 /
 *
 * 使用场景：Organization Console 等需要 ADMIN 权限的页面。
 */
export default function ManagerRoute({
  children,
  allowedRoles = ['ROOT', 'ADMIN'],
}: ManagerRouteProps) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />

  const userState = useAuthStore.getState().userState
  if (!userState) return <Navigate to="/login" replace />

  if (!allowedRoles.includes(userState.role)) {
    return <Navigate to="/" replace />
  }

  return <EnterpriseLayout>{children}</EnterpriseLayout>
}