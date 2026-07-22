import { useState } from 'react'
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
export default function WorkspacePage() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview')

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
            onClick={() => setActiveTab(t.key)}
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