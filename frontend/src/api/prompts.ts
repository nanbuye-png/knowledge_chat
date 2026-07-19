import apiClient from './client'

export interface PromptTemplate {
  id: number
  name: string
  prompt_type: string
  content: string
  version: number
  enabled: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PromptVersion {
  id: number
  template_id: number
  version: number
  content: string
  created_at: string
}

export interface PromptCreate {
  name: string
  prompt_type: string
  content: string
  version?: number
  enabled?: boolean
  is_active?: boolean
}

export interface PromptUpdate {
  name?: string
  prompt_type?: string
  content?: string
  enabled?: boolean
  is_active?: boolean
}

export async function listPrompts(): Promise<PromptTemplate[]> {
  const { data } = await apiClient.get('/prompt-templates')
  return data
}

export async function getPrompt(id: number): Promise<PromptTemplate> {
  const { data } = await apiClient.get(`/prompt-templates/${id}`)
  return data
}

export async function createPrompt(p: PromptCreate): Promise<PromptTemplate> {
  const { data } = await apiClient.post('/prompt-templates', p)
  return data
}

export async function updatePrompt(id: number, p: PromptUpdate): Promise<PromptTemplate> {
  const { data } = await apiClient.put(`/prompt-templates/${id}`, p)
  return data
}

export async function deletePrompt(id: number): Promise<void> {
  await apiClient.delete(`/prompt-templates/${id}`)
}

export async function getVersions(templateId: number): Promise<PromptVersion[]> {
  const { data } = await apiClient.get(`/prompt-templates/${templateId}/versions`)
  return data
}

export async function rollbackPrompt(templateId: number, version: number): Promise<PromptTemplate> {
  const { data } = await apiClient.post(`/prompt-templates/${templateId}/versions/${version}/rollback`)
  return data
}