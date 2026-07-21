import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Trash2, MessageSquare, BookOpen, ArrowLeft } from 'lucide-react'
import { useKnowledgeChatStore } from '../../contexts/KnowledgeChatContext'
import { useAuthStore } from '../../store/auth'
import * as knowledgeApi from '../../api/knowledge'
import * as conversationsApi from '../../api/conversations'
import * as kbApi from '../../api/knowledgeBases'
import type { Message, SourceReference, Conversation } from '../../types'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import ChatMessage from '../chat/ChatMessage'
import InputBox from '../chat/InputBox'
import ConversationList from '../../components/Conversation/ConversationList'

export default function KnowledgeChatPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const knowledgeBaseId = Number(id)

  const { fetchUser } = useAuthStore()
  const {
    messages, isStreaming, addMessage, updateLastMessage, setStreaming, clearMessages,
    setCurrentConversationId, currentConversationId, conversationList, setConversationList,
    loadMessages, setSources, currentSources,
  } = useKnowledgeChatStore()

  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<Conversation | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => { fetchUser() }, [fetchUser])

  useEffect(() => {
    kbApi.listKnowledgeBases()
      .then((list) => {
        const kb = list.find(k => k.id === knowledgeBaseId)
        if (kb) setKnowledgeBase(kb)
        else navigate('/knowledge', { replace: true })
      })
      .catch(() => navigate('/knowledge', { replace: true }))
  }, [knowledgeBaseId])

  useEffect(() => {
    conversationsApi.listConversations(knowledgeBaseId)
      .then(data => setConversationList(data))
      .catch(() => {})
  }, [knowledgeBaseId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    setSources([])

    try {
      let sources: SourceReference[] = []
      let fullContent = ''

      knowledgeApi.createStreamKnowledgeQuery(
        content,
        knowledgeBaseId,
        (srcs) => {
          sources = srcs
          setSources(srcs)
        },
        (token) => {
          fullContent += token
          updateLastMessage(fullContent)
        },
        () => {
          // Attach sources to the last message
          const state = useKnowledgeChatStore.getState()
          const msgs = [...state.messages]
          const lastMsg = msgs[msgs.length - 1]
          if (lastMsg) {
            lastMsg.sources = sources
            lastMsg.hasKnowledge = sources.length > 0
            useKnowledgeChatStore.setState({ messages: msgs })
          }
          setStreaming(false)
          conversationsApi.listConversations(knowledgeBaseId)
            .then(data => setConversationList(data))
            .catch(() => {})
        },
        (error) => {
          updateLastMessage(`抱歉，查询出错：${error}`)
          setStreaming(false)
        },
        currentConversationId ?? undefined,
      )
    } catch (error: any) {
      updateLastMessage(`抱歉，处理请求时出错：${error.message || '未知错误'}`)
      setStreaming(false)
    }
  }, [isStreaming, knowledgeBaseId, addMessage, updateLastMessage, setStreaming, currentConversationId, setSources])

  const handleNewChat = useCallback(async () => {
    if (!knowledgeBaseId) return
    try {
      const conv = await conversationsApi.createConversation(knowledgeBaseId)
      setCurrentConversationId(conv.id)
      const data = await conversationsApi.listConversations(knowledgeBaseId)
      setConversationList(data)
      clearMessages()
    } catch {}
  }, [knowledgeBaseId, setCurrentConversationId, clearMessages])

  const handleSelectConversation = useCallback(async (conv: Conversation) => {
    setCurrentConversationId(conv.id)
    try {
      const serverMessages = await conversationsApi.getConversationMessages(conv.id)
      const converted: Message[] = serverMessages.map((m: any) => ({
        id: m.id, role: m.role, content: m.content, timestamp: new Date(m.created_at).getTime(),
      }))
      loadMessages(converted)
    } catch {}
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
      const data = await conversationsApi.listConversations(knowledgeBaseId)
      setConversationList(data)
      if (conv.id === currentConversationId) {
        setCurrentConversationId(null)
        clearMessages()
      }
    } catch {}
  }, [showDeleteConfirm, knowledgeBaseId, currentConversationId])

  const handleRenameConversation = useCallback(async (id: number, title: string) => {
    try {
      await conversationsApi.renameConversation(id, title)
      const data = await conversationsApi.listConversations(knowledgeBaseId)
      setConversationList(data)
    } catch {}
  }, [knowledgeBaseId])

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800 text-slate-800 dark:text-slate-100">
      <header className="h-12 flex-shrink-0 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl 
                        border-b border-slate-200 dark:border-slate-700 flex items-center px-4 z-40">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/knowledge')}
            className="p-1 rounded-lg text-slate-400 hover:text-primary-500 
                       hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <BookOpen className="w-5 h-5 text-primary-500" />
          <span className="font-semibold text-slate-800 dark:text-slate-100 text-sm">
            {knowledgeBase?.name || '知识库问答'}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 
                          dark:bg-primary-900/30 dark:text-primary-300 font-medium">
            Knowledge RAG
          </span>
        </div>
        <div className="flex-1" />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 flex-shrink-0 bg-white/50 dark:bg-slate-900/50 border-r border-slate-200 dark:border-slate-700 overflow-y-auto">
          <ConversationList
            conversationList={conversationList}
            searchKeyword=""
            onSelectConversation={handleSelectConversation}
            currentConversationId={currentConversationId}
            onDeleteConversation={handleDeleteConversation}
            onRenameConversation={handleRenameConversation}
            onNewChat={handleNewChat}
          />
        </aside>

        <main className="flex-1 flex flex-col min-w-0">
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
                      <BookOpen className="w-10 h-10 text-primary-500" />
                    </div>
                    <h2 className="text-xl font-semibold text-slate-600 dark:text-slate-300 mb-2">
                      知识库问答
                    </h2>
                    <p className="text-sm text-center max-w-md text-slate-400">
                      {knowledgeBase?.name
                        ? `正在基于「${knowledgeBase.name}」进行问答`
                        : '基于知识库内容回答你的问题'}
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
                onUpload={() => {}}
                disabled={isStreaming}
                mode="knowledge"
              />
            </div>
          </div>
        </main>
      </div>

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