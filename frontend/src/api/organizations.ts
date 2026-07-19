import apiClient from './client'

export interface Organization {
  id: number
  name: string
  slug: string
  description: string | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface OrganizationListResponse {
  items: Organization[]
  total: number
}

export interface OrganizationMember {
  id: number
  organization_id: number
  user_id: number
  role: string
  joined_at: string | null
  is_active: boolean
}

export async function listOrganizations(skip = 0, limit = 20): Promise<OrganizationListResponse> {
  const { data } = await apiClient.get('/admin/organizations', { params: { skip, limit } })
  return data
}

export async function getOrganization(orgId: number): Promise<Organization> {
  const { data } = await apiClient.get(`/admin/organizations/${orgId}`)
  return data
}

export async function createOrganization(payload: { name: string; slug: string; description?: string }): Promise<Organization> {
  const { data } = await apiClient.post('/admin/organizations', payload)
  return data
}

export async function updateOrganization(orgId: number, payload: Partial<Organization>): Promise<Organization> {
  const { data } = await apiClient.put(`/admin/organizations/${orgId}`, payload)
  return data
}

export async function deleteOrganization(orgId: number): Promise<void> {
  await apiClient.delete(`/admin/organizations/${orgId}`)
}

// ---- Members ----

export async function listMembers(orgId: number, skip = 0, limit = 50): Promise<OrganizationMember[]> {
  const { data } = await apiClient.get(`/admin/organizations/${orgId}/members`, { params: { skip, limit } })
  return data
}

export async function addMember(orgId: number, userId: number, role = 'MEMBER'): Promise<OrganizationMember> {
  const { data } = await apiClient.post(`/admin/organizations/${orgId}/members`, { user_id: userId, role })
  return data
}

export async function updateMemberRole(orgId: number, userId: number, role: string): Promise<OrganizationMember> {
  const { data } = await apiClient.put(`/admin/organizations/${orgId}/members/${userId}`, { role })
  return data
}

export async function removeMember(orgId: number, userId: number): Promise<void> {
  await apiClient.delete(`/admin/organizations/${orgId}/members/${userId}`)
}