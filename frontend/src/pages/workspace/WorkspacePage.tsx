import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { LayoutDashboard, MessageSquare, BookOpen, FileText } from 'lucide-react'
import WorkspaceOverview from './WorkspaceOverview'
import ChatPage from '../chat/ChatPage'
import KnowledgePage from '../knowledge/KnowledgePage'
import DocumentPage from '../documents/DocumentPage'

type WorkspaceTab = 'overview' | 'chat' | 'knowledge' | 'documents'

/**
 * USER 工作空间页面。
 * 包含 Overview Dashboard + Chat + Knowledge + Documents 标签切换。
 */
const VALID_TABS: WorkspaceTab[] = ['overview', 'chat', 'knowledge', 'documents']

export default function WorkspacePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab') as WorkspaceTab | null
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(
    tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'overview'
  )

  const handleTabChange = (tab: WorkspaceTab) => {
    setActiveTab(tab)
    setSearchParams({ tab }, { replace: true })
  }

  const tabs = [
    { key: 'overview' as WorkspaceTab, label: '概览', icon: LayoutDashboard },
    { key: 'chat' as WorkspaceTab, label: 'AI 对话', icon: MessageSquare },
    { key: 'knowledge' as WorkspaceTab, label: '知识库', icon: BookOpen },
    { key: 'documents' as WorkspaceTab, label: '文档', icon: FileText },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Tab navigation */}
      <div className="flex-shrink-0 flex items-center gap-1 px-4 pt-3 pb-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => handleTabChange(t.key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-t-lg transition-colors
              ${activeTab === t.key
                ? 'bg-slate-50 dark:bg-slate-700 text-primary-600 dark:text-primary-400 font-medium border-b-2 border-primary-500'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'overview' && <WorkspaceOverview />}
        {activeTab === 'chat' && <ChatPage />}
        {activeTab === 'knowledge' && <KnowledgePage />}
        {activeTab === 'documents' && <DocumentPage />}
      </div>
    </div>
  )
}