import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Trash2, MessageSquare, Brain, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useChatStore } from '../../contexts/ChatContext'
import { useDocumentStore } from '../../contexts/DocumentContext'
import { useThemeStore } from '../../contexts/ThemeContext'
import { useAuthStore } from '../../store/auth'
import * as chatApi from '../../api/chat'
import * as documentsApi from '../../api/documents'
import * as kbApi from '../../api/knowledgeBases'
import * as conversationsApi from '../../api/conversations'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import type { Message, SourceReference, UploadProgress, Conversation } from '../../types'
import ChatMessage from './ChatMessage'
import InputBox from './InputBox'
import PipelinePanel from './PipelinePanel'
import Sidebar from '../../components/Layout/Sidebar'
import KnowledgeBaseList from '../../components/KnowledgeBase/KnowledgeBaseList'
import ConversationList from '../../components/Conversation/ConversationList'

export default function ChatPage() {
  const { user, fetchUser, logout } = useAuthStore()
  const { messages, mode, isStreaming, addMessage, updateLastMessage, setMode, setStreaming, clearMessages,
    setCurrentConversationId, currentConversationId, conversationList, setConversationList, loadMessages } = useChatStore()
  const { documents, loading: docsLoading, fetchDocuments, addDocument, removeDocument, updateDocumentStatus } = useDocumentStore()
  const { theme } = useThemeStore()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [pipelineOpen, setPipelineOpen] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<Conversation | null>(null)
  const [searchKeyword, setSearchKeyword] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [kbLoading, setKbLoading] = useState(false)
  const [currentKnowledgeBase, setCurrentKnowledgeBase] = useState<KnowledgeBase | null>(null)

  // Fetch user
  useEffect(() => { fetchUser() }, [fetchUser])

  // Fetch KBs
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

  // When KB changes, fetch docs/conversations
  useEffect(() => {
    if (currentKnowledgeBase) {
      fetchDocuments(currentKnowledgeBase.id)
      conversationsApi.listConversations(currentKnowledgeBase.id)
        .then(data => setConversationList(data))
        .catch((err: any) => console.error('Failed to fetch conversations:', err))
    } else {
      setConversationList([])
    }
  }, [currentKnowledgeBase, fetchDocuments])

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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

  const handleSend = useCallback(async (content: string) => {
    if (!content.trim() || isStreaming) return

    const userMessage: Message = {
      id: Date.now().toString(), role: 'user', content, timestamp: Date.now(),
    }
    addMessage(userMessage)

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(), role: 'assistant', content: '', timestamp: Date.now(),
    }
    addMessage(assistantMessage)
    setStreaming(true)

    try {
      if (mode === 'knowledge') {
        let sources: SourceReference[] = []
        let fullContent = ''

        chatApi.createStreamKnowledgeQuery(
          content,
          currentKnowledgeBase?.id || 0,
          (srcs) => { sources = srcs },
          (token) => {
            fullContent += token
            updateLastMessage(fullContent)
          },
          () => {
            const state = useChatStore.getState()
            const msg = state.messages
            const lastMsg = msg[msg.length - 1]
            if (lastMsg) {
              lastMsg.sources = sources
              lastMsg.hasKnowledge = sources.length > 0
              useChatStore.setState({ messages: [...msg] })
            }
            setStreaming(false)
            if (currentKnowledgeBase) {
              conversationsApi.listConversations(currentKnowledgeBase.id)
                .then(data => setConversationList(data))
                .catch(() => {})
            }
          },
          (error) => {
            updateLastMessage(`抱歉，查询出错：${error}`)
            setStreaming(false)
          },
          currentConversationId ?? undefined,
        )
      } else {
        let fullContent = ''
        const state = useChatStore.getState()
        const history = state.messages.filter(m => (m.role as string) !== 'system').slice(-10).map(m => ({
          role: m.role, content: m.content,
        }))

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
  }, [isStreaming, mode, addMessage, updateLastMessage, setStreaming, currentKnowledgeBase, currentConversationId])

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

  const handleNewChat = useCallback(async () => {
    if (!currentKnowledgeBase) return
    try {
      const conv = await conversationsApi.createConversation(currentKnowledgeBase.id)
      setCurrentConversationId(conv.id)
      const data = await conversationsApi.listConversations(currentKnowledgeBase.id)
      setConversationList(data)
      clearMessages()
    } catch (err: any) { console.error('Failed to create conversation:', err) }
  }, [currentKnowledgeBase, setCurrentConversationId, clearMessages])

  const handleSelectConversation = useCallback(async (conv: Conversation) => {
    setCurrentConversationId(conv.id)
    try {
      const serverMessages = await conversationsApi.getConversationMessages(conv.id)
      const converted: Message[] = serverMessages.map((m: any) => ({
        id: m.id, role: m.role, content: m.content, timestamp: new Date(m.created_at).getTime(),
      }))
      loadMessages(converted)
    } catch (err: any) { console.error('Failed to load messages:', err) }
  }, [setCurrentConversationId, loadMessages])

  const handleDeleteConversation = useCallback(async (conv: Conversation) => {
    setShowDeleteConfirm(conv)
  }, [])

  const confirmDeleteConversation = useCallback(async () => {
    if (!showDeleteConfirm) return
    const conv = showDeleteConfirm
    setShowDeleteConfirm(null)
    try {
      await conversationsApi.deleteConversation(conv.id)
      if (currentKnowledgeBase) {
        const data = await conversationsApi.listConversations(currentKnowledgeBase.id)
        setConversationList(data)
      }
      if (conv.id === currentConversationId) {
        setCurrentConversationId(null)
        clearMessages()
      }
    } catch (err: any) { console.error('Failed to delete conversation:', err) }
  }, [showDeleteConfirm, currentKnowledgeBase, currentConversationId])

  const handleRenameConversation = useCallback(async (id: number, title: string) => {
    try {
      await conversationsApi.renameConversation(id, title)
      if (currentKnowledgeBase) {
        const data = await conversationsApi.listConversations(currentKnowledgeBase.id)
        setConversationList(data)
      }
    } catch (err: any) { console.error('Failed to rename conversation:', err) }
  }, [currentKnowledgeBase])

  const handleModeToggle = useCallback(async (newMode: 'knowledge' | 'chat') => {
    setMode(newMode)
    try { await chatApi.setMode(newMode) } catch {}
  }, [setMode])

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800 text-slate-800 dark:text-slate-100">
      {/* Top bar */}
      <header className="h-12 flex-shrink-0 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl 
                        border-b border-slate-200 dark:border-slate-700 flex items-center px-4 z-40">
        <div className="flex items-center gap-3">
          <MessageSquare className="w-5 h-5 text-primary-500" />
          <span className="font-semibold text-slate-800 dark:text-slate-100 text-sm">AI Chat</span>
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
            mode === 'knowledge'
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
              : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
          }`}>
            {mode === 'knowledge' ? 'Knowledge RAG' : 'General Chat'}
          </span>
        </div>

        <div className="flex-1" />

        {/* KB selector */}
        <div className="flex items-center gap-2">
          {mode === 'knowledge' && (
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
          )}

          {/* Mode toggle */}
          <button
            onClick={() => handleModeToggle(mode === 'knowledge' ? 'chat' : 'knowledge')}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 
                       text-slate-500 hover:text-primary-500 hover:bg-primary-50 
                       dark:hover:bg-primary-900/20 transition-colors"
          >
            {mode === 'knowledge' ? '💬 Chat' : '📚 Knowledge'}
          </button>

          {/* Pipeline toggle */}
          <button
            onClick={() => setPipelineOpen(!pipelineOpen)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 
                       hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            title="AI Pipeline"
          >
            {pipelineOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          documents={documents}
          loading={docsLoading}
          uploadProgress={uploadProgress}
          isOpen={sidebarOpen}
          onDelete={handleDelete}
          onRefresh={() => currentKnowledgeBase && fetchDocuments(currentKnowledgeBase.id)}
          onUpload={() => {
            // Trigger hidden file input
            const input = document.createElement('input')
            input.type = 'file'
            input.accept = '.pdf,.docx,.doc,.md,.txt'
            input.onchange = (e) => {
              const file = (e.target as HTMLInputElement).files?.[0]
              if (file) handleUpload(file)
            }
            input.click()
          }}
          knowledgeBases={knowledgeBases}
          kbLoading={kbLoading}
          onCreateKB={async (name) => {
            try {
              const created = await kbApi.createKnowledgeBase({ name })
              setKnowledgeBases(prev => [created, ...prev])
            } catch {}
          }}
          onRenameKB={async (id, name) => {
            try {
              const updated = await kbApi.updateKnowledgeBase(id, { name })
              setKnowledgeBases(prev => prev.map(kb => kb.id === id ? updated : kb))
            } catch {}
          }}
          onDeleteKB={async (id) => {
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
          selectedKbId={currentKnowledgeBase?.id ?? null}
          onSelectKB={(kb) => setCurrentKnowledgeBase(kb)}
          searchKeyword={searchKeyword}
          onSearchChange={setSearchKeyword}
          conversationList={conversationList}
          onNewChat={handleNewChat}
          onSelectConversation={handleSelectConversation}
          currentConversationId={currentConversationId}
          onDeleteConversation={handleDeleteConversation}
          onRenameConversation={handleRenameConversation}
        />

        {/* Main chat area */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Messages — min-h-0 prevents flex overflow */}
          <div className="flex-1 overflow-y-auto px-4 py-6 scrollbar-thin min-h-0">
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
                    <p className="text-sm text-center max-w-md text-slate-400">
                      {mode === 'knowledge'
                        ? '上传文档到知识库，AI 可以基于文档内容回答你的问题'
                        : '有什么想聊的？我可以和你讨论各种话题'}
                    </p>
                  </motion.div>
                ) : (
                  <>
                    {messages.map((msg, idx) => (
                      <ChatMessage
                        key={msg.id}
                        message={msg}
                        isStreaming={isStreaming && idx === messages.length - 1 && msg.role === 'assistant'}
                      />
                    ))}
                    <div ref={messagesEndRef} />
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 border-t border-slate-200 dark:border-slate-700 
                          bg-white/50 dark:bg-slate-900/50 backdrop-blur-xl">
            <div className="max-w-4xl mx-auto px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                {messages.length > 0 && (
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    清空对话
                  </button>
                )}
              </div>
              <InputBox
                onSend={handleSend}
                onUpload={handleUpload}
                disabled={isStreaming}
                mode={mode}
              />
            </div>
          </div>
        </main>

        {/* Pipeline Panel */}
        <PipelinePanel open={pipelineOpen} onToggle={() => setPipelineOpen(!pipelineOpen)} />
      </div>

      {/* Clear confirm modal */}
      <AnimatePresence>
        {showClearConfirm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center"
            onClick={() => setShowClearConfirm(false)}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-2xl max-w-sm mx-4">
              <h3 className="text-lg font-semibold mb-2">清空对话</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">确定要清空所有对话记录吗？</p>
              <div className="flex gap-3 justify-end">
                <button onClick={() => setShowClearConfirm(false)}
                  className="px-4 py-2 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700">
                  取消
                </button>
                <button onClick={() => { clearMessages(); setShowClearConfirm(false) }}
                  className="px-4 py-2 rounded-xl text-sm font-medium bg-red-500 text-white hover:bg-red-600">
                  确认清空
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}

        {showDeleteConfirm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center"
            onClick={() => setShowDeleteConfirm(null)}>
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-2xl max-w-sm mx-4">
              <h3 className="text-lg font-semibold mb-2">删除会话</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">确定删除该会话吗？</p>
              <div className="flex gap-3 justify-end">
                <button onClick={() => setShowDeleteConfirm(null)}
                  className="px-4 py-2 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700">
                  取消
                </button>
                <button onClick={confirmDeleteConversation}
                  className="px-4 py-2 rounded-xl text-sm font-medium bg-red-500 text-white hover:bg-red-600">
                  删除
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}