import { useMemo } from 'react'
import type { Conversation } from '../../types'

interface ConversationListProps {
  conversationList: Conversation[]
  searchKeyword: string
  onSelectConversation: (conversation: Conversation) => void
  currentConversationId: number | null
  onDeleteConversation: (conversation: Conversation) => void
  onRenameConversation: (conversation: Conversation) => void
}

export default function ConversationList({
  conversationList,
  searchKeyword,
  onSelectConversation,
  currentConversationId,
  onDeleteConversation,
  onRenameConversation,
}: ConversationListProps) {
  const filteredConversation = useMemo(() => {
    const keyword = searchKeyword.trim().toLowerCase()

    if (!keyword) return conversationList

    return conversationList.filter((item) =>
      (item.title ?? '').toLowerCase().includes(keyword)
    )
  }, [conversationList, searchKeyword])

  if (filteredConversation.length === 0) {
    return (
      <div className="text-center text-sm text-slate-400 dark:text-slate-500 py-8">
        {searchKeyword.trim() ? '没有匹配的会话' : '暂无会话记录'}
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
          <span className="block truncate pr-14">{conv.title || '新会话'}</span>
          {/* Hover actions */}
          <span className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5">
            <button
              onClick={(e) => { e.stopPropagation(); onRenameConversation(conv) }}
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
        </div>
      ))}
    </div>
  )
}
