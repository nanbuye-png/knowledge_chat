import apiClient from './client'
import type { Conversation } from '../types'

export async function listConversations(knowledgeBaseId: number): Promise<Conversation[]> {
  const response = await apiClient.get('/conversations', {
    params: { knowledge_base_id: knowledgeBaseId },
  })
  return response.data
}

export async function createConversation(knowledgeBaseId: number): Promise<Conversation> {
  const response = await apiClient.post('/conversations', { knowledge_base_id: knowledgeBaseId })
  return response.data
}
