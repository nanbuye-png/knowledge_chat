import apiClient from './client'

export interface PromptTemplate {
  id: number
  name: string
  prompt_type: string
  content: string
  version: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export async function listPrompts(): Promise<PromptTemplate[]> {
  const { data } = await apiClient.get('/prompt-templates')
  return data
}

export async function createPrompt(body: { name: string; prompt_type: string; content: string }): Promise<PromptTemplate> {
  const { data } = await apiClient.post('/prompt-templates', body)
  return data
}

export async function updatePrompt(id: number, body: Record<string, any>): Promise<PromptTemplate> {
  const { data } = await apiClient.put(`/prompt-templates/${id}`, body)
  return data
}

export async function deletePrompt(id: number): Promise<void> {
  await apiClient.delete(`/prompt-templates/${id}`)
}