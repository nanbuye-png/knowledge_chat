import apiClient from './client'

export interface LLMModel {
  id: number
  name: string
  provider: string
  model_name: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface LLMModelCreate {
  name: string
  provider: string
  model_name: string
}

export interface LLMModelUpdate {
  name?: string
  provider?: string
  model_name?: string
  enabled?: boolean
}

export async function listModels(): Promise<LLMModel[]> {
  const { data } = await apiClient.get('/llm-models')
  return data
}

export async function getModel(id: number): Promise<LLMModel> {
  const { data } = await apiClient.get(`/llm-models/${id}`)
  return data
}

export async function createModel(model: LLMModelCreate): Promise<LLMModel> {
  const { data } = await apiClient.post('/llm-models', model)
  return data
}

export async function updateModel(id: number, model: LLMModelUpdate): Promise<LLMModel> {
  const { data } = await apiClient.put(`/llm-models/${id}`, model)
  return data
}

export async function deleteModel(id: number): Promise<void> {
  await apiClient.delete(`/llm-models/${id}`)
}