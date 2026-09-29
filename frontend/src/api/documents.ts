import apiClient from './client'
import type { Document, UploadResult } from '../types'

export async function fetchDocuments(knowledgeBaseId: number): Promise<Document[]> {
  const response = await apiClient.get('/documents', { params: { knowledge_base_id: knowledgeBaseId } })
  return response.data.documents
}

/**
 * 上传文档。
 *
 * 后端响应契约（Phase 3 §5.3 幂等）：``skipped=true`` 表示同一知识库内已有
 * 内容完全相同的文档 —— 本次**没有**新建记录、也没有派发处理任务，
 * ``duplicated_of`` 指向被复用的文档 ID。调用方必须据此区分
 * "新上传（要轮询状态）" 与 "被跳过（可直接复用既有记录）"。
 */
export async function uploadDocument(file: File, knowledgeBaseId: number): Promise<UploadResult> {
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