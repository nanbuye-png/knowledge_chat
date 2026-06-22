import apiClient from './client'
import type { Document } from '../types'

export async function fetchDocuments(): Promise<Document[]> {
  const response = await apiClient.get('/documents')
  return response.data.documents
}

export async function uploadDocument(file: File): Promise<{ document_id: string; filename: string; status: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // 2 minutes for upload
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