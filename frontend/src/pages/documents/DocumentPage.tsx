import { useState, useEffect, useCallback } from 'react'
import { FileText, Upload } from 'lucide-react'
import { useDocumentStore } from '../../contexts/DocumentContext'
import * as documentsApi from '../../api/documents'
import * as kbApi from '../../api/knowledgeBases'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import type { UploadProgress } from '../../types'
import DocumentList from '../../components/Documents/DocumentList'

export default function DocumentPage() {
  const { documents, loading, fetchDocuments, addDocument, removeDocument, updateDocumentStatus } = useDocumentStore()

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [currentKnowledgeBase, setCurrentKnowledgeBase] = useState<KnowledgeBase | null>(null)
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null)

  const fetchKnowledgeBases = useCallback(async () => {
    try {
      const data = await kbApi.listKnowledgeBases()
      setKnowledgeBases(data)
      if (data.length > 0) {
        setCurrentKnowledgeBase(prev => {
          if (prev && data.find(kb => kb.id === prev.id)) return prev
          return data[0]
        })
      }
    } catch (err: any) {
      console.error('Failed to fetch KBs:', err)
    }
  }, [])

  useEffect(() => { fetchKnowledgeBases() }, [fetchKnowledgeBases])

  useEffect(() => {
    if (currentKnowledgeBase) {
      fetchDocuments(currentKnowledgeBase.id)
    }
  }, [currentKnowledgeBase, fetchDocuments])

  // Poll processing documents
  useEffect(() => {
    const processingDocs = documents.filter(d => d.status === 'processing')
    if (processingDocs.length === 0) return
    const interval = setInterval(async () => {
      for (const doc of processingDocs) {
        try {
          const updated = await documentsApi.getDocumentStatus(doc.id)
          if (updated.status !== 'processing') {
            updateDocumentStatus(doc.id, updated.status, updated.chunk_count)
          }
        } catch {}
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [documents, updateDocumentStatus])

  const handleUpload = useCallback(async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    const allowed = ['pdf', 'docx', 'doc', 'md', 'txt', 'xlsx', 'csv']
    if (!ext || !allowed.includes(ext)) {
      alert(`不支持的文件类型。支持: ${allowed.join(', ')}`)
      return
    }
    setUploadProgress({ filename: file.name, progress: 0, status: 'uploading' })
    try {
      if (!currentKnowledgeBase) {
        alert('请先选择或创建一个知识库')
        return
      }
      const result = await documentsApi.uploadDocument(file, currentKnowledgeBase.id)
      setUploadProgress({ filename: file.name, progress: 100, status: 'processing' })
      addDocument({
        id: result.document_id, filename: result.filename,
        file_size: file.size, file_type: `.${ext}`,
        status: 'processing', chunk_count: 0, created_at: new Date().toISOString(),
      })
      const pollInterval = setInterval(async () => {
        try {
          const updated = await documentsApi.getDocumentStatus(result.document_id)
          if (updated.status !== 'processing') {
            updateDocumentStatus(result.document_id, updated.status, updated.chunk_count)
            setUploadProgress({
              filename: file.name, progress: 100,
              status: updated.status === 'completed' ? 'completed' : 'failed',
              error: updated.error_message || undefined,
            })
            clearInterval(pollInterval)
            setTimeout(() => setUploadProgress(null), 3000)
          }
        } catch { clearInterval(pollInterval) }
      }, 2000)
    } catch (error: any) {
      setUploadProgress({ filename: file.name, progress: 100, status: 'failed', error: error.message || '上传失败' })
      setTimeout(() => setUploadProgress(null), 3000)
    }
  }, [addDocument, updateDocumentStatus, currentKnowledgeBase])

  const handleDelete = useCallback(async (id: string) => {
    try { await documentsApi.deleteDocument(id); removeDocument(id) }
    catch (error: any) { alert(error.message || '删除失败') }
  }, [removeDocument])

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800 text-slate-800 dark:text-slate-100">
      {/* Top bar */}
      <header className="h-12 flex-shrink-0 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl 
                        border-b border-slate-200 dark:border-slate-700 flex items-center px-4 z-40">
        <div className="flex items-center gap-3">
          <FileText className="w-5 h-5 text-primary-500" />
          <span className="font-semibold text-slate-800 dark:text-slate-100 text-sm">文档管理</span>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <select
            value={currentKnowledgeBase?.id || ''}
            onChange={(e) => {
              const kb = knowledgeBases.find(k => k.id === Number(e.target.value))
              if (kb) setCurrentKnowledgeBase(kb)
            }}
            className="text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 
                       rounded-lg px-2 py-1.5 text-slate-600 dark:text-slate-300 outline-none"
          >
            {knowledgeBases.map(kb => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </select>

          <button
            onClick={() => {
              const input = document.createElement('input')
              input.type = 'file'
              input.accept = '.pdf,.docx,.doc,.md,.txt'
              input.onchange = (e) => {
                const file = (e.target as HTMLInputElement).files?.[0]
                if (file) handleUpload(file)
              }
              input.click()
            }}
            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-primary-500 
                       text-white hover:bg-primary-600 transition-colors"
          >
            <Upload className="w-3.5 h-3.5" />
            上传文档
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6">
          {currentKnowledgeBase ? (
            <div className="bg-white/50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
              <DocumentList
                documents={documents}
                loading={loading}
                uploadProgress={uploadProgress}
                onDelete={handleDelete}
                onRefresh={() => currentKnowledgeBase && fetchDocuments(currentKnowledgeBase.id)}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-[60vh] text-slate-400">
              <FileText className="w-16 h-16 mb-4 text-slate-300 dark:text-slate-600" />
              <p className="text-lg font-medium text-slate-500 dark:text-slate-400 mb-2">暂无知识库</p>
              <p className="text-sm">请先在知识库页面创建知识库</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}