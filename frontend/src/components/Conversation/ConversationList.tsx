import { useMemo, useState, useRef, useEffect } from 'react'
import type { Conversation } from '../../types'

interface ConversationListProps {
  conversationList: Conversation[]
  searchKeyword: string
  onSelectConversation: (conversation: Conversation) => void
  currentConversationId: number | null
  onDeleteConversation: (conversation: Conversation) => void
  onRenameConversation: (id: number, title: string) => Promise<void>
  onNewChat: () => void
}

export default function ConversationList({
  conversationList,
  searchKeyword,
  onSelectConversation,
  currentConversationId,
  onDeleteConversation,
  onRenameConversation,
  onNewChat,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filteredConversation = useMemo(() => {
    const keyword = searchKeyword.trim().toLowerCase()
    if (!keyword) return conversationList
    return conversationList.filter((item) =>
      (item.title ?? '').toLowerCase().includes(keyword)
    )
  }, [conversationList, searchKeyword])

  // Auto-focus input when editing starts
  useEffect(() => {
    if (editingId !== null && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editingId])

  const startEditing = (conv: Conversation) => {
    setEditingId(conv.id)
    setEditValue(conv.title || '')
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditValue('')
  }

  const confirmRename = async () => {
    if (editingId === null) return
    const trimmed = editValue.trim()
    if (!trimmed) {
      cancelEditing()
      return
    }
    await onRenameConversation(editingId, trimmed)
    setEditingId(null)
    setEditValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      confirmRename()
    } else if (e.key === 'Escape') {
      cancelEditing()
    }
  }

  if (filteredConversation.length === 0) {
    if (searchKeyword.trim()) {
      return (
        <div className="text-center text-sm text-slate-400 dark:text-slate-500 py-8">
          没有匹配的会话
        </div>
      )
    }
    // No conversations at all → empty state
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
          <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <p className="text-sm text-slate-400 dark:text-slate-500 mb-3">
          暂无聊天记录
        </p>
        <button
          onClick={onNewChat}
          className="px-4 py-2 text-xs font-medium text-white bg-gradient-to-r from-emerald-500 to-teal-500 rounded-lg
                     shadow-sm hover:shadow-md transition-all duration-200 active:scale-[0.98]"
        >
          开始新的知识库问答
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {filteredConversation.map((conv) => (
        <div
          key={conv.id}
          onClick={() => onSelectConversation(conv)}
          className={`group relative px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors truncate ${
            conv.id === currentConversationId
              ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
              : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          {editingId === conv.id ? (
            <div className="flex items-center gap-1">
              <input
                ref={inputRef}
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={() => {
                  // Small delay to allow button clicks to register
                  setTimeout(cancelEditing, 150)
                }}
                className="flex-1 min-w-0 px-1.5 py-0.5 text-sm rounded border border-primary-400 
                           bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100
                           focus:outline-none focus:ring-1 focus:ring-primary-500"
                onClick={(e) => e.stopPropagation()}
              />
              <button
                onMouseDown={(e) => { e.preventDefault(); confirmRename() }}
                className="px-1 text-xs text-emerald-500 hover:text-emerald-600"
                title="确认"
              >
                ✓
              </button>
              <button
                onMouseDown={(e) => { e.preventDefault(); cancelEditing() }}
                className="px-1 text-xs text-slate-400 hover:text-red-500"
                title="取消"
              >
                ✕
              </button>
            </div>
          ) : (
            <>
              <span className="block truncate pr-14">{conv.title || '新会话'}</span>
              {/* Hover actions */}
              <span className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5">
                <button
                  onClick={(e) => { e.stopPropagation(); startEditing(conv) }}
                  className="px-1.5 py-0.5 text-xs rounded hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-500 dark:text-slate-400"
                  title="重命名"
                >
                  ✏️
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onDeleteConversation(conv) }}
                  className="px-1.5 py-0.5 text-xs rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-slate-500 dark:text-slate-400"
                  title="删除"
                >
                  🗑️
                </button>
              </span>
            </>
          )}
        </div>
      ))}
    </div>
  )
}