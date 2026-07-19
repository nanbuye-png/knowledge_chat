import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ChatPage from '../pages/chat/ChatPage'
import Login from '../pages/Login'
import Register from '../pages/Register'
import Usage from '../pages/Usage'
import Prompts from '../pages/Prompts'
import DashboardPage from '../pages/admin/DashboardPage'
import UserManagementPage from '../pages/admin/UserManagementPage'
import OnlineMonitorPage from '../pages/admin/OnlineMonitorPage'
import UsageDashboardPage from '../pages/admin/UsageDashboardPage'
import AuditLogs from '../pages/admin/AuditLogs'
import AuditLogsPage from '../pages/admin/AuditLogsPage'
import SecurityDashboardPage from '../pages/admin/SecurityDashboardPage'
import OrganizationConsole from '../pages/organization/OrganizationConsole'
import OrganizationMembersPage from '../pages/organization/Members'
import OrganizationDepartments from '../pages/organization/Departments'
import MembersPage from '../pages/organization/MembersPage'
import ACLPage from '../pages/organization/ACLPage'
import OrgUsagePage from '../pages/organization/UsagePage'
import KnowledgeACL from '../pages/knowledge/ACL'
import KnowledgeACLPage from '../pages/knowledge/KnowledgeACLPage'
import KnowledgeSettingsPage from '../pages/knowledge/KnowledgeSettingsPage'
import QuotaPage from '../pages/quota/QuotaPage'
import SystemConfig from '../pages/admin/SystemConfig'
import ApiKeys from '../pages/admin/ApiKeys'
import AIModels from '../pages/ai/Models'
import AIEmbedding from '../pages/ai/Embedding'
import AIRetrieval from '../pages/ai/Retrieval'
import AIAgent from '../pages/ai/Agent'
import ModelRegistryPage from '../pages/ai/ModelRegistryPage'
import ProviderManagementPage from '../pages/ai/ProviderManagementPage'
import PromptManagementPage from '../pages/ai/PromptManagementPage'
import AIConfigPage from '../pages/ai/AIConfigPage'
import AgentManagementPage from '../pages/ai/AgentManagementPage'
import WorkflowManagementPage from '../pages/ai/WorkflowManagementPage'
import ToolRegistryPage from '../pages/ai/ToolRegistryPage'
import MonitoringDashboard from '../pages/monitoring/Dashboard'
import MonitoringDashboardPage from '../pages/monitoring/MonitoringDashboardPage'
import AIMetricsPage from '../pages/monitoring/AIMetricsPage'
import TokenAnalyticsPage from '../pages/monitoring/TokenAnalyticsPage'
import APIPerformancePage from '../pages/monitoring/APIPerformancePage'
import ErrorTrackingPage from '../pages/monitoring/ErrorTrackingPage'
import EnterpriseLayout from '../layout/EnterpriseLayout'
import WorkspaceLayout from '../layouts/WorkspaceLayout'
import { useAuthStore } from '../store/auth'
import { usePermission } from '../hooks/usePermission'
import RoleRoute from './RoleRoute'
import ForbiddenPage from '../pages/error/403'
import PlatformPage from '../pages/platform/PlatformPage'
import WorkspacePage from '../pages/workspace/WorkspacePage'
import AccountLayout from '../layouts/AccountLayout'
import ModelCenterPage from '../pages/platform/models/ModelCenterPage'
import PromptStudioPage from '../pages/platform/prompts/PromptStudioPage'
import AgentStudioPage from '../pages/platform/agents/AgentStudioPage'
import WorkflowStudioPage from '../pages/platform/workflows/WorkflowStudioPage'
import OrganizationModelsPage from '../pages/organization/models/OrganizationModelsPage'
import ProfilePage from '../pages/account/ProfilePage'
import SecurityPage from '../pages/account/SecurityPage'
import SessionsPage from '../pages/account/SessionsPage'
import ApiKeysPage from '../pages/account/ApiKeysPage'
import { redirectByRole } from './roleRouter'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  const userState = useAuthStore.getState().userState
  if (!userState || userState.role !== 'ROOT') return <Navigate to="/" replace />
  return <EnterpriseLayout>{children}</EnterpriseLayout>
}

function ManagerRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  const userState = useAuthStore.getState().userState
  if (!userState || (userState.role !== 'ROOT' && userState.role !== 'ADMIN'))
    return <Navigate to="/" replace />
  return <EnterpriseLayout>{children}</EnterpriseLayout>
}

// 首页根路径根据角色自动跳转
function HomeRedirect() {
  const { userState, isAuthenticated, fetchUser } = useAuthStore()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      setReady(true)
      return
    }
    if (userState) {
      setReady(true)
      return
    }
    fetchUser().finally(() => setReady(true))
  }, [])

  if (!ready) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!userState) {
    return <Navigate to="/login" replace />
  }

  return <Navigate to={redirectByRole(userState.role)} replace />
}

export default function AppRouter() {
  const { fetchUser, token, isAuthenticated } = useAuthStore()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (token && !isAuthenticated) {
      fetchUser().finally(() => setReady(true))
    } else {
      setReady(true)
    }
  }, [])

  if (!ready) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/403" element={<ForbiddenPage />} />
      <Route path="/usage" element={<ProtectedRoute><Usage /></ProtectedRoute>} />
      <Route path="/prompts" element={<ProtectedRoute><Prompts /></ProtectedRoute>} />

      {/* Platform Console - ROOT only */}
      <Route path="/platform" element={
        <RoleRoute allowedRoles={['ROOT']}>
          <EnterpriseLayout><PlatformPage /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/platform/models" element={
        <RoleRoute allowedRoles={['ROOT']}>
          <EnterpriseLayout><ModelCenterPage /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/platform/prompts" element={
        <RoleRoute allowedRoles={['ROOT']}>
          <EnterpriseLayout><PromptStudioPage /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/platform/agents" element={
        <RoleRoute allowedRoles={['ROOT']}>
          <EnterpriseLayout><AgentStudioPage /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/platform/workflows" element={
        <RoleRoute allowedRoles={['ROOT']}>
          <EnterpriseLayout><WorkflowStudioPage /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/organization/models" element={
        <RoleRoute allowedRoles={['ROOT', 'ADMIN']}>
          <EnterpriseLayout><OrganizationModelsPage /></EnterpriseLayout>
        </RoleRoute>
      } />

      {/* Organization Console - ROOT & ADMIN */}
      <Route path="/organization" element={
        <RoleRoute allowedRoles={['ROOT', 'ADMIN']}>
          <EnterpriseLayout><OrganizationConsole /></EnterpriseLayout>
        </RoleRoute>
      } />
      <Route path="/organization/members" element={<ManagerRoute><MembersPage /></ManagerRoute>} />
      <Route path="/organization/departments" element={<ManagerRoute><OrganizationDepartments /></ManagerRoute>} />

      {/* Workspace - All roles */}
      <Route path="/workspace" element={
        <RoleRoute allowedRoles={['ROOT', 'ADMIN', 'USER']}>
          <EnterpriseLayout><WorkspacePage /></EnterpriseLayout>
        </RoleRoute>
      } />

      {/* Admin routes - ROOT only */}
      <Route path="/admin" element={<AdminRoute><DashboardPage /></AdminRoute>} />
      <Route path="/admin/users" element={<AdminRoute><UserManagementPage /></AdminRoute>} />
      <Route path="/admin/system" element={<AdminRoute><SystemConfig /></AdminRoute>} />
      <Route path="/admin/api-keys" element={<AdminRoute><ApiKeys /></AdminRoute>} />
      <Route path="/admin/online" element={<AdminRoute><OnlineMonitorPage /></AdminRoute>} />
      <Route path="/admin/usage" element={<AdminRoute><UsageDashboardPage /></AdminRoute>} />

      {/* Knowledge Management - Manager */}
      <Route path="/knowledge/acl" element={<ManagerRoute><KnowledgeACLPage /></ManagerRoute>} />
      <Route path="/knowledge/settings" element={<ManagerRoute><KnowledgeSettingsPage /></ManagerRoute>} />

      {/* Quota - Manager */}
      <Route path="/quota" element={<ManagerRoute><QuotaPage /></ManagerRoute>} />

      {/* AI Center - Manager (ROOT + ADMIN) */}
      <Route path="/ai/models" element={<ManagerRoute><ModelRegistryPage /></ManagerRoute>} />
      <Route path="/ai/providers" element={<ManagerRoute><ProviderManagementPage /></ManagerRoute>} />
      <Route path="/ai/prompts" element={<ManagerRoute><PromptManagementPage /></ManagerRoute>} />
      <Route path="/ai/config" element={<ManagerRoute><AIConfigPage /></ManagerRoute>} />
      <Route path="/ai/agents" element={<ManagerRoute><AgentManagementPage /></ManagerRoute>} />
      <Route path="/ai/workflows" element={<ManagerRoute><WorkflowManagementPage /></ManagerRoute>} />
      <Route path="/ai/tools" element={<ManagerRoute><ToolRegistryPage /></ManagerRoute>} />

      {/* Security Center - ROOT only */}
      <Route path="/admin/security" element={<AdminRoute><SecurityDashboardPage /></AdminRoute>} />
      <Route path="/admin/audit" element={<AdminRoute><AuditLogsPage /></AdminRoute>} />

      {/* Monitoring Center - ROOT only */}
      <Route path="/monitoring" element={<AdminRoute><MonitoringDashboardPage /></AdminRoute>} />
      <Route path="/monitoring/ai" element={<AdminRoute><AIMetricsPage /></AdminRoute>} />
      <Route path="/monitoring/token" element={<AdminRoute><TokenAnalyticsPage /></AdminRoute>} />
      <Route path="/monitoring/api" element={<AdminRoute><APIPerformancePage /></AdminRoute>} />
      <Route path="/monitoring/errors" element={<AdminRoute><ErrorTrackingPage /></AdminRoute>} />

      {/* Account Center - All authenticated */}
      <Route path="/account/profile" element={<ProtectedRoute><EnterpriseLayout><AccountLayout><ProfilePage /></AccountLayout></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/account/security" element={<ProtectedRoute><EnterpriseLayout><AccountLayout><SecurityPage /></AccountLayout></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/account/sessions" element={<ProtectedRoute><EnterpriseLayout><AccountLayout><SessionsPage /></AccountLayout></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/account/api-keys" element={<ProtectedRoute><EnterpriseLayout><AccountLayout><ApiKeysPage /></AccountLayout></EnterpriseLayout></ProtectedRoute>} />

      {/* Home - role based redirect */}
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
    </Routes>
  )
}