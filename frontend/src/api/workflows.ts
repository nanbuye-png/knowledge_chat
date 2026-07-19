import apiClient from './client'

export interface WorkflowNode {
  id: string
  type: 'start' | 'end' | 'prompt' | 'llm' | 'knowledge' | 'agent' | 'tool'
  label: string
  config: Record<string, any>
}

export interface Workflow {
  id: number
  name: string
  description: string
  nodes: WorkflowNode[]
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface WorkflowCreate {
  name: string
  description: string
  nodes?: WorkflowNode[]
  enabled?: boolean
}

export interface WorkflowUpdate {
  name?: string
  description?: string
  nodes?: WorkflowNode[]
  enabled?: boolean
}

export async function listWorkflows(): Promise<Workflow[]> {
  const { data } = await apiClient.get('/workflows')
  return data
}

export async function getWorkflow(id: number): Promise<Workflow> {
  const { data } = await apiClient.get(`/workflows/${id}`)
  return data
}

export async function createWorkflow(w: WorkflowCreate): Promise<Workflow> {
  const { data } = await apiClient.post('/workflows', w)
  return data
}

export async function updateWorkflow(id: number, w: WorkflowUpdate): Promise<Workflow> {
  const { data } = await apiClient.put(`/workflows/${id}`, w)
  return data
}

export async function deleteWorkflow(id: number): Promise<void> {
  await apiClient.delete(`/workflows/${id}`)
}

export async function executeWorkflow(id: number, input: string): Promise<{ result: string; steps: any[] }> {
  const { data } = await apiClient.post(`/workflows/${id}/execute`, { input })
  return data
}