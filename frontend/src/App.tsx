import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Trash2, MessageSquare } from 'lucide-react'
import Navbar from './components/Layout/Navbar'
import Sidebar from './components/Layout/Sidebar'
import ChatBubble from './components/Chat/ChatBubble'
import ChatInput from './components/Chat/ChatInput'
import { TypingIndicator } from './components/UI/LoadingSpinner'
import { useChatStore } from './contexts/ChatContext'
import { useDocumentStore } from './contexts/DocumentContext'
import { useThemeStore } from './contexts/ThemeContext'
import * as chatApi from './api/chat'
import * as documentsApi from './api/documents'
import * as kbApi from './api/knowledgeBases'
import type { KnowledgeBase } from './api/knowledgeBases'
import type { Message, SourceReference, UploadProgress } from './types'

export default function App() {
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login', { replace: true })
  }

  const { messages, mode, isStreaming, addMessage, updateLastMessage, setMode, setStreaming, clearMessages } = useChatStore()
  const { documents, loading: docsLoading, fetchDocuments, addDocument, removeDocument, updateDocumentStatus } = useDocumentStore()
  const { theme } = useThemeStore()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Knowledge base state
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [kbLoading, setKbLoading] = useState(false)
  const [currentKnowledgeBase, setCurrentKnowledgeBase] = useState<KnowledgeBase | null>(null)

  // Fetch knowledge bases
  const fetchKnowledgeBases = useCallback(async () => {
    setKbLoading(true)
    try {
      const data = await kbApi.listKnowledgeBases()
      setKnowledgeBases(data)
      // Auto-select first KB if none selected
      if (data.length > 0) {
        setCurrentKnowledgeBase((prev) => {
          if (prev && data.find(kb => kb.id === prev.id)) return prev
          return data[0]
        })
      }
    } catch (err: any) {
      console.error('Failed to fetch knowledge bases:', err)
    } finally {
      setKbLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchKnowledgeBases()
  }, [fetchKnowledgeBases])

  // When currentKnowledgeBase changes, fetch its documents
  useEffect(() => {
    if (currentKnowledgeBase) {
      fetchDocuments(currentKnowledgeBase.id)
    }
  }, [currentKnowledgeBase, fetchDocuments])

  // Handle KB selection
  const handleSelectKB = useCallback((kb: KnowledgeBase) => {
    setCurrentKnowledgeBase(kb)
  }, [])

  // Knowledge base CRUD handlers
  const handleCreateKB = useCallback(async (name: string) => {
    try {
      const created = await kbApi.createKnowledgeBase({ name })
      setKnowledgeBases(prev => [created, ...prev])
    } catch (err: any) {
      alert(err?.response?.data?.detail || '创建知识库失败')
    }
  }, [])

  const handleRenameKB = useCallback(async (id: number, name: string) => {
    try {
      const updated = await kbApi.updateKnowledgeBase(id, { name })
      setKnowledgeBases(prev => prev.map(kb => kb.id === id ? updated : kb))
    } catch (err: any) {
      alert(err?.response?.data?.detail || '重命名失败')
    }
  }, [])

  const handleDeleteKB = useCallback(async (id: number) => {
    try {
      await kbApi.deleteKnowledgeBase(id)
      setKnowledgeBases(prev => {
        const updated = prev.filter(kb => kb.id !== id)
        // If deleting the selected KB, switch to first remaining
        setCurrentKnowledgeBase(current => {
          if (current?.id === id) {
            return updated.length > 0 ? updated[0] : null
          }
          return current
        })
        return updated
      })
    } catch (err: any) {
      alert(err?.response?.data?.detail || '删除失败')
    }
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Poll document status for processing documents
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

  // Handle sending a message
  const handleSend = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    addMessage(userMessage)

    // Add placeholder for assistant
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    }
    addMessage(assistantMessage)
    setStreaming(true)

    try {
      if (mode === 'knowledge') {
        // Knowledge mode with streaming
        let sources: SourceReference[] = []
        let fullContent = ''

        chatApi.createStreamKnowledgeQuery(
          content,
          (srcs) => { sources = srcs },
          (token) => {
            fullContent += token
            updateLastMessage(fullContent)
          },
          () => {
            // Update message with sources
            const state = useChatStore.getState()
            const msg = state.messages
            const lastMsg = msg[msg.length - 1]
            if (lastMsg) {
              lastMsg.sources = sources
              lastMsg.hasKnowledge = sources.length > 0
              useChatStore.setState({ messagesByMode: { ...state.messagesByMode, [mode]: [...msg] }, messages: [...msg] })
            }
            setStreaming(false)
          },
          (error) => {
            updateLastMessage(`抱歉，查询出错：${error}`)
            setStreaming(false)
          }
        )
      } else {
        // Chat mode with streaming - use only current mode's messages for history
        const state = useChatStore.getState()
        const currentModeMessages = state.messagesByMode[mode] || []
        const history = currentModeMessages.slice(-10).map(m => ({
          role: m.role,
          content: m.content,
        }))

        let fullContent = ''
        chatApi.createStreamChat(
          content,
          history,
          (token) => {
            fullContent += token
            updateLastMessage(fullContent)
          },
          () => setStreaming(false),
          (error) => {
            updateLastMessage(`抱歉，对话出错：${error}`)
            setStreaming(false)
          }
        )
      }
    } catch (error: any) {
      updateLastMessage(`抱歉，处理请求时出错：${error.message || '未知错误'}`)
      setStreaming(false)
    }
  }, [isStreaming, mode, addMessage, updateLastMessage, setStreaming])

  // Handle file upload
  const handleUpload = useCallback(async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    const allowed = ['pdf', 'docx', 'doc', 'md', 'txt']
    if (!ext || !allowed.includes(ext)) {
      alert(`不支持的文件类型。支持: ${allowed.join(', ')}`)
      return
    }

    setUploadProgress({
      filename: file.name,
      progress: 0,
      status: 'uploading',
    })

    try {
      if (!currentKnowledgeBase) {
        alert('请先选择或创建一个知识库')
        return
      }
      const result = await documentsApi.uploadDocument(file, currentKnowledgeBase.id)
      setUploadProgress({
        filename: file.name,
        progress: 100,
        status: 'processing',
      })

      // Add to document list
      addDocument({
        id: result.document_id,
        filename: result.filename,
        file_size: file.size,
        file_type: `.${ext}`,
        status: 'processing',
        chunk_count: 0,
        created_at: new Date().toISOString(),
      })

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const updated = await documentsApi.getDocumentStatus(result.document_id)
          if (updated.status !== 'processing') {
            updateDocumentStatus(result.document_id, updated.status, updated.chunk_count)
            setUploadProgress({
              filename: file.name,
              progress: 100,
              status: updated.status === 'completed' ? 'completed' : 'failed',
              error: updated.error_message || undefined,
            })
            clearInterval(pollInterval)
            setTimeout(() => setUploadProgress(null), 3000)
          }
        } catch {
          clearInterval(pollInterval)
        }
      }, 2000)

    } catch (error: any) {
      setUploadProgress({
        filename: file.name,
        progress: 100,
        status: 'failed',
        error: error.message || '上传失败',
      })
      setTimeout(() => setUploadProgress(null), 3000)
    }
  }, [addDocument, updateDocumentStatus, currentKnowledgeBase])

  // Handle delete document
  const handleDelete = useCallback(async (id: string) => {
    try {
      await documentsApi.deleteDocument(id)
      removeDocument(id)
    } catch (error: any) {
      alert(error.message || '删除失败')
    }
  }, [removeDocument])

  // Handle mode toggle
  const handleModeToggle = useCallback(async (newMode: 'knowledge' | 'chat') => {
    setMode(newMode)
    try {
      await chatApi.setMode(newMode)
    } catch {}
  }, [setMode])

  // Handle clear messages
  const handleClearMessages = () => {
    clearMessages()
    setShowClearConfirm(false)
  }

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800 text-slate-800 dark:text-slate-100">
      {/* Navbar */}
      <Navbar
        mode={mode}
        sidebarOpen={sidebarOpen}
        onToggleMode={handleModeToggle}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        onLogout={handleLogout}
      />

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          documents={documents}
          loading={docsLoading}
          uploadProgress={uploadProgress}
          isOpen={sidebarOpen}
          onDelete={handleDelete}
          onRefresh={() => currentKnowledgeBase && fetchDocuments(currentKnowledgeBase.id)}
          onUpload={() => fileInputRef.current?.click()}
          knowledgeBases={knowledgeBases}
          kbLoading={kbLoading}
          onCreateKB={handleCreateKB}
          onRenameKB={handleRenameKB}
          onDeleteKB={handleDeleteKB}
          selectedKbId={currentKnowledgeBase?.id ?? null}
          onSelectKB={handleSelectKB}
        />

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.md,.txt"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleUpload(file)
            e.target.value = ''
          }}
        />

        {/* Chat area */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6 scrollbar-thin">
            <div className="max-w-4xl mx-auto">
              <AnimatePresence mode="popLayout">
                {messages.length === 0 ? (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col items-center justify-center h-[60vh] text-slate-400"
                  >
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-100 to-purple-100 
                                  dark:from-primary-900/30 dark:to-purple-900/30 
                                  flex items-center justify-center mb-6 shadow-lg">
                      <MessageSquare className="w-10 h-10 text-primary-500" />
                    </div>
                    <h2 className="text-xl font-semibold text-slate-600 dark:text-slate-300 mb-2">
                      {mode === 'knowledge' ? '知识库问答' : 'AI 闲聊'}
                    </h2>
                    <p className="text-sm text-center max-w-md">
                      {mode === 'knowledge'
                        ? '上传文档到知识库，我可以基于文档内容回答你的问题'
                        : '有什么想聊的？我可以和你讨论各种话题'}
                    </p>
                    {mode === 'knowledge' && (
                      <div className="flex gap-2 mt-6">
                        {['上传一份文档', '问一个关于文档的问题', '查看文档列表'].map((hint, i) => (
                          <span key={i} className="px-3 py-1.5 text-xs rounded-full 
                                                   bg-slate-100 dark:bg-slate-800 
                                                   text-slate-500 dark:text-slate-400">
                            {hint}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <>
                    {messages.map((msg) => (
                      <ChatBubble
                        key={msg.id}
                        message={msg}
                        isStreaming={isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'}
                      />
                    ))}
                    {isStreaming && messages[messages.length - 1]?.content === '' && (
                      <TypingIndicator />
                    )}
                  </>
                )}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 border-t border-slate-200 dark:border-slate-700 
                          bg-white/50 dark:bg-slate-900/50 backdrop-blur-xl">
            <div className="max-w-4xl mx-auto px-4 py-4">
              <div className="flex items-center gap-2 mb-2">
                {/* Clear chat button */}
                {messages.length > 0 && (
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    清空对话
                  </button>
                )}
                <span className={`text-xs ml-auto ${
                  mode === 'knowledge' 
                    ? 'text-primary-500' 
                    : 'text-slate-400'
                }`}>
                  {mode === 'knowledge' ? '📚 知识库模式' : '💬 闲聊模式'}
                </span>
              </div>
              <ChatInput
                onSend={handleSend}
                onUpload={handleUpload}
                disabled={isStreaming}
                placeholder={
                  mode === 'knowledge'
                    ? '输入你的问题，我将基于知识库回答...'
                    : '随便聊聊吧...'
                }
              />
            </div>
          </div>
        </main>
      </div>

      {/* Clear confirmation dialog */}
      <AnimatePresence>
        {showClearConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center"
            onClick={() => setShowClearConfirm(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-2xl max-w-sm mx-4"
            >
              <h3 className="text-lg font-semibold mb-2">清空对话</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                确定要清空所有对话记录吗？此操作不可撤销。
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="px-4 py-2 rounded-xl text-sm font-medium
                             text-slate-600 dark:text-slate-300
                             hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleClearMessages}
                  className="px-4 py-2 rounded-xl text-sm font-medium
                             bg-red-500 text-white hover:bg-red-600 transition-colors"
                >
                  确认清空
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}