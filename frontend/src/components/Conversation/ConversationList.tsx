import { useMemo } from 'react'
import type { Conversation } from '../../types'

interface ConversationListProps {
  conversationList: Conversation[]
  searchKeyword: string
}

export default function ConversationList({
  conversationList,
  searchKeyword,
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
          className="px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-300
                     hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer
                     transition-colors truncate"
        >
          {conv.title || '新会话'}
        </div>
      ))}
    </div>
  )
}