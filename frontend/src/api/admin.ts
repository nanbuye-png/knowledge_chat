import apiClient from './client'

export interface DashboardData {
  users: {
    total: number
    active: number
    disabled: number
    root_count: number
    admin_count: number
  }
  online: {
    online_users: number
  }
  knowledge: {
    total: number
  }
  documents: {
    total: number
  }
  chunks: {
    total: number
  }
  embeddings: {
    total: number
    available: boolean
  }
  usage: {
    today_requests: number
    today_prompt_tokens: number
    today_completion_tokens: number
    today_total_tokens: number
    today_cost: number
  }
  system: {
    cpu_usage: number | null
    memory_usage: number | null
    disk_usage: number | null
  }
}

export interface DashboardOverview {
  users_count: number
  knowledge_bases_count: number
  documents_count: number
  conversations_count: number
  messages_count: number
}

export interface SystemMonitorStatus {
  cpu_usage: number | null
  memory_usage: number | null
  disk_usage: number | null
  uptime: string | null
  python_version: string | null
  platform: string | null
  timestamp: string | null
}

export interface UserListItem {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  created_at: string | null
}

export interface UserOnlineItem {
  id: number
  username: string
  role: string
  is_active: boolean
  last_activity_at: string | null
  online: boolean
}

export async function getDashboard(): Promise<DashboardData> {
  const response = await apiClient.get('/admin/dashboard')
  return response.data
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const response = await apiClient.get('/admin/dashboard/overview')
  return response.data
}

export async function getSystemMonitorStatus(): Promise<SystemMonitorStatus> {
  const response = await apiClient.get('/admin/dashboard/system')
  return response.data
}

export async function listUsers(): Promise<UserListItem[]> {
  const response = await apiClient.get('/admin/users')
  return response.data
}

export async function listOnlineUsers(): Promise<UserOnlineItem[]> {
  const response = await apiClient.get('/admin/users/online')
  return response.data
}

export async function updateUserStatus(userId: number, isActive: boolean): Promise<void> {
  await apiClient.patch(`/admin/users/${userId}/status`, { is_active: isActive })
}

export async function updateUserRole(userId: number, role: string): Promise<void> {
  await apiClient.patch(`/admin/users/${userId}/role`, { role })
}

export async function deleteUser(userId: number): Promise<void> {
  await apiClient.delete(`/admin/users/${userId}`)
}