import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ChatPage from '../pages/chat/ChatPage'
import Login from '../pages/Login'
import Register from '../pages/Register'
import Usage from '../pages/Usage'
import Prompts from '../pages/Prompts'
import AdminDashboard from '../pages/admin/AdminDashboard'
import UserManagement from '../pages/admin/UserManagement'
import AuditLogs from '../pages/admin/AuditLogs'
import OrganizationPage from '../pages/organization/Organizations'
import OrganizationMembers from '../pages/organization/Members'
import OrganizationDepartments from '../pages/organization/Departments'
import KnowledgeACL from '../pages/knowledge/ACL'
import QuotaPage from '../pages/quota/QuotaPage'
import SystemConfig from '../pages/admin/SystemConfig'
import ApiKeys from '../pages/admin/ApiKeys'
import AIModels from '../pages/ai/Models'
import AIEmbedding from '../pages/ai/Embedding'
import AIRetrieval from '../pages/ai/Retrieval'
import AIAgent from '../pages/ai/Agent'
import MonitoringDashboard from '../pages/monitoring/Dashboard'
import EnterpriseLayout from '../layout/EnterpriseLayout'
import { useAuthStore } from '../store/auth'
import { usePermission } from '../hooks/usePermission'

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
      <Route path="/usage" element={<ProtectedRoute><Usage /></ProtectedRoute>} />
      <Route path="/prompts" element={<ProtectedRoute><Prompts /></ProtectedRoute>} />

      {/* Admin routes - ROOT only */}
      <Route path="/admin" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
      <Route path="/admin/users" element={<AdminRoute><UserManagement /></AdminRoute>} />
      <Route path="/admin/system" element={<AdminRoute><SystemConfig /></AdminRoute>} />
      <Route path="/admin/api-keys" element={<AdminRoute><ApiKeys /></AdminRoute>} />

      {/* Manager routes - ROOT & ADMIN */}
      <Route path="/organization" element={<ManagerRoute><OrganizationPage /></ManagerRoute>} />
      <Route path="/organization/members" element={<ManagerRoute><OrganizationMembers /></ManagerRoute>} />
      <Route path="/organization/departments" element={<ManagerRoute><OrganizationDepartments /></ManagerRoute>} />

      {/* Knowledge ACL - Manager */}
      <Route path="/knowledge/acl" element={<ManagerRoute><KnowledgeACL /></ManagerRoute>} />

      {/* Quota - Manager */}
      <Route path="/quota" element={<ManagerRoute><QuotaPage /></ManagerRoute>} />

      {/* AI Console - All roles */}
      <Route path="/ai/models" element={<ProtectedRoute><EnterpriseLayout><AIModels /></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/ai/embedding" element={<ProtectedRoute><EnterpriseLayout><AIEmbedding /></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/ai/retrieval" element={<ProtectedRoute><EnterpriseLayout><AIRetrieval /></EnterpriseLayout></ProtectedRoute>} />
      <Route path="/ai/agent" element={<ProtectedRoute><EnterpriseLayout><AIAgent /></EnterpriseLayout></ProtectedRoute>} />

      {/* Monitoring */}
      {/* Audit Log */}
      <Route path="/admin/audit" element={<AdminRoute><AuditLogs /></AdminRoute>} />

      {/* Monitoring */}
      <Route path="/monitoring" element={<AdminRoute><MonitoringDashboard /></AdminRoute>} />

      {/* Main chat route */}
      <Route path="/" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
    </Routes>
  )
}