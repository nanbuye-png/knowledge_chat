import apiClient from './client'

export interface Agent {
  id: number
  name: string
  description: string
  model_id: number
  prompt_id: number
  knowledge_base_id: number | null
  tools: string[]
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentCreate {
  name: string
  description: string
  model_id: number
  prompt_id: number
  knowledge_base_id?: number | null
  tools?: string[]
  enabled?: boolean
}

export interface AgentUpdate {
  name?: string
  description?: string
  model_id?: number
  prompt_id?: number
  knowledge_base_id?: number | null
  tools?: string[]
  enabled?: boolean
}

export async function listAgents(): Promise<Agent[]> {
  const { data } = await apiClient.get('/agents')
  return data
}

export async function getAgent(id: number): Promise<Agent> {
  const { data } = await apiClient.get(`/agents/${id}`)
  return data
}

export async function createAgent(a: AgentCreate): Promise<Agent> {
  const { data } = await apiClient.post('/agents', a)
  return data
}

export async function updateAgent(id: number, a: AgentUpdate): Promise<Agent> {
  const { data } = await apiClient.put(`/agents/${id}`, a)
  return data
}

export async function deleteAgent(id: number): Promise<void> {
  await apiClient.delete(`/agents/${id}`)
}

export async function executeAgent(id: number, input: string): Promise<{ response: string; steps: any[]; citations: any[] }> {
  const { data } = await apiClient.post(`/agents/${id}/execute`, { input })
  return data
}