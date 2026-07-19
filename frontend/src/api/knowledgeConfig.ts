import apiClient from './client'

export interface KnowledgeConfig {
  knowledge_base_id: number
  chunk_size: number
  chunk_overlap: number
  embedding_provider: string | null
  embedding_model: string
  retrieval_top_k: number
  id: number | null
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeConfigUpdate {
  chunk_size?: number
  chunk_overlap?: number
  embedding_provider?: string | null
  embedding_model?: string
  retrieval_top_k?: number
}

export async function getKnowledgeConfig(knowledgeBaseId: number): Promise<KnowledgeConfig> {
  const { data } = await apiClient.get(`/knowledge-bases/${knowledgeBaseId}/config`)
  return data
}

export async function updateKnowledgeConfig(
  knowledgeBaseId: number,
  payload: KnowledgeConfigUpdate,
): Promise<KnowledgeConfig> {
  const { data } = await apiClient.put(`/knowledge-bases/${knowledgeBaseId}/config`, payload)
  return data
}