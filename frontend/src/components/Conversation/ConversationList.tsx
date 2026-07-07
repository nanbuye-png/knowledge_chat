import { useMemo } from 'react'
import type { Conversation } from '../../types'

interface ConversationListProps {
  conversationList: Conversation[]
  searchKeyword: string
  onSelectConversation: (conversation: Conversation) => void
  currentConversationId: number | null
}

export default function ConversationList({
  conversationList,
  searchKeyword,
  onSelectConversation,
  currentConversationId,
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
          className={`px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors truncate ${
            conv.id === currentConversationId
              ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
              : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          {conv.title || '新会话'}
        </div>
      ))}
    </div>
  )
}