import apiClient from './client'
import type { Document } from '../types'

export async function fetchDocuments(knowledgeBaseId: number): Promise<Document[]> {
  const response = await apiClient.get('/documents', { params: { knowledge_base_id: knowledgeBaseId } })
  return response.data.documents
}

export async function uploadDocument(file: File, knowledgeBaseId: number): Promise<{ document_id: string; filename: string; status: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // 2 minutes for upload
    params: { knowledge_base_id: knowledgeBaseId },
  })
  return response.data
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient.delete(`/documents/${id}`)
}

export async function getDocumentStatus(id: string): Promise<Document> {
  const response = await apiClient.get(`/documents/${id}/status`)
  return response.data
}