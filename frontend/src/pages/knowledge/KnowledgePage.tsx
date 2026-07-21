import { useState, useEffect, useCallback } from 'react'
import { BookOpen, Upload, Search, Plus, Trash2, FileText, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useDocumentStore } from '../../contexts/DocumentContext'
import * as documentsApi from '../../api/documents'
import * as kbApi from '../../api/knowledgeBases'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import type { Document, UploadProgress } from '../../types'
import DocumentList from '../../components/Documents/DocumentList'
import KnowledgeBaseList from '../../components/KnowledgeBase/KnowledgeBaseList'

export default function KnowledgePage() {
  const navigate = useNavigate()
  const { documents, loading: docsLoading, fetchDocuments, addDocument, removeDocument, updateDocumentStatus } = useDocumentStore()

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [kbLoading, setKbLoading] = useState(false)
  const [currentKnowledgeBase, setCurrentKnowledgeBase] = useState<KnowledgeBase | null>(null)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null)

  const fetchKnowledgeBases = useCallback(async () => {
    setKbLoading(true)
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
    } finally { setKbLoading(false) }
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
          <BookOpen className="w-5 h-5 text-primary-500" />
          <span className="font-semibold text-slate-800 dark:text-slate-100 text-sm">知识库</span>
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

          {/* Upload button */}
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

      <div className="flex flex-1 overflow-hidden">
        {/* KB sidebar */}
        <aside className={`flex-shrink-0 w-64 bg-white/50 dark:bg-slate-900/50 border-r border-slate-200 dark:border-slate-700 overflow-hidden`}>
          <div className="h-full overflow-y-auto p-3 space-y-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                placeholder="搜索知识库..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg bg-slate-100 dark:bg-slate-800 
                           border border-slate-200 dark:border-slate-700 outline-none
                           text-slate-600 dark:text-slate-300 placeholder-slate-400"
              />
            </div>

            {/* KB List */}
            <KnowledgeBaseList
              knowledgeBases={knowledgeBases}
              loading={kbLoading}
              selectedId={currentKnowledgeBase?.id ?? null}
              onSelect={(kb) => setCurrentKnowledgeBase(kb)}
              onCreate={async (name) => {
                try {
                  const created = await kbApi.createKnowledgeBase({ name })
                  setKnowledgeBases(prev => [created, ...prev])
                } catch {}
              }}
              onRename={async (id, name) => {
                try {
                  const updated = await kbApi.updateKnowledgeBase(id, { name })
                  setKnowledgeBases(prev => prev.map(kb => kb.id === id ? updated : kb))
                } catch {}
              }}
              onDelete={async (id) => {
                try {
                  await kbApi.deleteKnowledgeBase(id)
                  setKnowledgeBases(prev => {
                    const updated = prev.filter(kb => kb.id !== id)
                    setCurrentKnowledgeBase(current => {
                      if (current?.id === id) return updated.length > 0 ? updated[0] : null
                      return current
                    })
                    return updated
                  })
                } catch {}
              }}
            />

            {/* Document List */}
            {currentKnowledgeBase && (
              <div className="pt-3 border-t border-slate-200 dark:border-slate-700">
                <DocumentList
                  documents={documents}
                  loading={docsLoading}
                  uploadProgress={uploadProgress}
                  onDelete={handleDelete}
                  onRefresh={() => currentKnowledgeBase && fetchDocuments(currentKnowledgeBase.id)}
                />
              </div>
            )}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col items-center justify-center text-slate-400 min-w-0">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-100 to-purple-100 
                        dark:from-primary-900/30 dark:to-purple-900/30 
                        flex items-center justify-center mb-6 shadow-lg">
            <BookOpen className="w-10 h-10 text-primary-500" />
          </div>
          <h2 className="text-xl font-semibold text-slate-600 dark:text-slate-300 mb-2">
            知识库管理
          </h2>
          <p className="text-sm text-center max-w-md text-slate-400 mb-6">
            选择左侧知识库，或上传文档开始构建你的知识库
          </p>
          {currentKnowledgeBase && (
            <button
              onClick={() => navigate(`/knowledge/${currentKnowledgeBase.id}/chat`)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary-500 text-white 
                         hover:bg-primary-600 transition-colors shadow-lg shadow-primary-500/25 text-sm font-medium"
            >
              <MessageSquare className="w-4 h-4" />
              进入问答
            </button>
          )}
          {uploadProgress && uploadProgress.status === 'completed' && (
            <p className="mt-4 text-xs text-green-500">上传完成！文档正在处理中...</p>
          )}
          {uploadProgress && uploadProgress.status === 'failed' && (
            <p className="mt-4 text-xs text-red-500">{uploadProgress.error || '上传失败'}</p>
          )}
        </main>
      </div>
    </div>
  )
}