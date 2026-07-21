import apiClient from './client'
import type { Conversation, ConversationMessage } from '../types'

export async function listConversations(knowledgeBaseId?: number | null): Promise<Conversation[]> {
  const params: Record<string, any> = {}
  if (knowledgeBaseId != null) {
    params.knowledge_base_id = knowledgeBaseId
  }
  const response = await apiClient.get('/conversations', { params })
  return response.data
}

export async function createConversation(knowledgeBaseId?: number | null): Promise<Conversation> {
  const response = await apiClient.post('/conversations', {
    knowledge_base_id: knowledgeBaseId ?? null,
  })
  return response.data
}

export async function getConversationMessages(conversationId: number): Promise<ConversationMessage[]> {
  const response = await apiClient.get(`/conversations/${conversationId}/messages`)
  return response.data
}

export async function deleteConversation(conversationId: number): Promise<void> {
  await apiClient.delete(`/conversations/${conversationId}`)
}

export async function renameConversation(conversationId: number, title: string): Promise<Conversation> {
  const response = await apiClient.patch(`/conversations/${conversationId}`, { title })
  return response.data
}
