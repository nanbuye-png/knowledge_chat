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

export interface SystemConfigData {
  llm_provider?: string
  llm_model?: string
  embedding_model?: string
  embedding_dim?: number
  chunk_size?: number
  chunk_overlap?: number
  rate_limit_window?: number
  rate_limit_chat?: number
  rate_limit_upload?: number
  [key: string]: any
}

// ---- System Config (TODO: backend endpoint not yet registered in main.py) ----
export async function getSystemConfig(): Promise<SystemConfigData> {
  // TODO: register /admin/system/config in main.py
  const response = await apiClient.get('/admin/system/config')
  return response.data
}

export async function updateSystemConfig(config: Record<string, any>): Promise<void> {
  // TODO: register /admin/system/config in main.py
  await apiClient.put('/admin/system/config', config)
}

// ---- API Keys (TODO: backend endpoint not yet registered in main.py) ----
export interface ApiKeyItem {
  id: number
  key: string
  user_id: number
  username: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
  call_count: number
}

export async function listApiKeys(): Promise<ApiKeyItem[]> {
  // TODO: register /admin/api-keys in main.py
  const response = await apiClient.get('/admin/api-keys')
  return response.data
}

export async function createApiKey(userId: number): Promise<{ key: string }> {
  // TODO: register /admin/api-keys in main.py
  const response = await apiClient.post('/admin/api-keys', { user_id: userId })
  return response.data
}

export async function revokeApiKey(keyId: number): Promise<void> {
  // TODO: register /admin/api-keys in main.py
  await apiClient.delete(`/admin/api-keys/${keyId}`)
}

// ---- Audit Logs (actual backend: /api/admin/audit-logs) ----
export interface AuditLogItem {
  id: number
  operator_id: number
  action: string
  target_type: string
  target_id: string | null
  detail: Record<string, any> | null
  ip_address: string | null
  user_agent: string | null
  status: string
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogItem[]
  total: number
  page: number
  page_size: number
}

export async function listAuditLogs(params?: { page?: number; page_size?: number }): Promise<AuditLogListResponse> {
  const response = await apiClient.get('/admin/audit-logs', { params })
  return response.data
}
