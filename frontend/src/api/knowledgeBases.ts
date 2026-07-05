import apiClient from './client'

export interface KnowledgeBase {
  id: number
  user_id: number
  name: string
  description: string | null
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeBaseCreate {
  name: string
  description?: string | null
}

export interface KnowledgeBaseUpdate {
  name?: string
  description?: string | null
}

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await apiClient.get('/knowledge-bases')
  return response.data
}

export async function createKnowledgeBase(data: KnowledgeBaseCreate): Promise<KnowledgeBase> {
  const response = await apiClient.post('/knowledge-bases', data)
  return response.data
}

export async function updateKnowledgeBase(id: number, data: KnowledgeBaseUpdate): Promise<KnowledgeBase> {
  const response = await apiClient.put(`/knowledge-bases/${id}`, data)
  return response.data
}

export async function deleteKnowledgeBase(id: number): Promise<void> {
  await apiClient.delete(`/knowledge-bases/${id}`)
}