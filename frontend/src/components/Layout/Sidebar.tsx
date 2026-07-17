import { motion } from 'framer-motion'
import { Upload, Search, Plus, Shield, Settings, Building2, Users as UsersIcon, LayoutDashboard, Key, FileText } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { Document, UploadProgress, Conversation } from '../../types'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import DocumentList from '../Documents/DocumentList'
import KnowledgeBaseList from '../KnowledgeBase/KnowledgeBaseList'
import ConversationList from '../Conversation/ConversationList'
import { usePermission } from '../../hooks/usePermission'

interface SidebarProps {
  documents: Document[]
  loading: boolean
  uploadProgress: UploadProgress | null
  isOpen: boolean
  onDelete: (id: string) => void
  onRefresh: () => void
  onUpload: () => void
  knowledgeBases: KnowledgeBase[]
  kbLoading: boolean
  onCreateKB: (name: string) => Promise<void>
  onRenameKB: (id: number, name: string) => Promise<void>
  onDeleteKB: (id: number) => Promise<void>
  selectedKbId: number | null
  onSelectKB: (kb: KnowledgeBase) => void
  searchKeyword: string
  onSearchChange: (value: string) => void
  conversationList: Conversation[]
  onNewChat: () => void
  onSelectConversation: (conversation: Conversation) => void
  currentConversationId: number | null
  onDeleteConversation: (conversation: Conversation) => void
  onRenameConversation: (id: number, title: string) => Promise<void>
}

export default function Sidebar({
  documents,
  loading,
  uploadProgress,
  isOpen,
  onDelete,
  onRefresh,
  onUpload,
  knowledgeBases,
  kbLoading,
  onCreateKB,
  onRenameKB,
  onDeleteKB,
  selectedKbId,
  onSelectKB,
  searchKeyword,
  onSearchChange,
  conversationList,
  onNewChat,
  onSelectConversation,
  currentConversationId,
  onDeleteConversation,
  onRenameConversation,
}: SidebarProps) {
  const navigate = useNavigate()
  const { isRoot, isAdmin } = usePermission()
  const canManage = isRoot() || isAdmin()

  const navItems = [
    ...(canManage
      ? [
          { label: '管理后台', icon: LayoutDashboard, path: '/admin', color: 'text-purple-500' },
          { label: '用户管理', icon: UsersIcon, path: '/admin/users', color: 'text-blue-500' },
          { label: '组织管理', icon: Building2, path: '/admin/organizations', color: 'text-emerald-500' },
          { label: '系统配置', icon: Settings, path: '/admin/system', color: 'text-orange-500' },
          { label: 'API Keys', icon: Key, path: '/admin/api-keys', color: 'text-cyan-500' },
        ]
      : []),
  ]

  return (
    <>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onRefresh}
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-30 lg:hidden"
        />
      )}

      <motion.aside
        initial={false}
        animate={{
          width: isOpen ? 300 : 0,
          opacity: isOpen ? 1 : 0,
        }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="fixed lg:relative z-40 lg:z-0 h-[calc(100vh-4rem)] 
                   bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-700
                   shadow-xl lg:shadow-none overflow-hidden flex-shrink-0"
      >
        <div className="w-[300px] h-full flex flex-col">
          {/* Admin Nav - role based */}
          {navItems.length > 0 && (
            <div className="px-3 pt-3 space-y-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-2 mb-1">
                Management
              </p>
              {navItems.map((item) => (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg
                             text-slate-600 dark:text-slate-300
                             hover:bg-slate-100 dark:hover:bg-slate-800
                             transition-colors"
                >
                  <item.icon className={`w-4 h-4 ${item.color}`} />
                  {item.label}
                </button>
              ))}
              <div className="border-t border-slate-200 dark:border-slate-700 my-2" />
            </div>
          )}

          {/* Knowledge Base section */}
          <div className="px-3">
            <KnowledgeBaseList
              knowledgeBases={knowledgeBases}
              loading={kbLoading}
              selectedId={selectedKbId}
              onSelect={onSelectKB}
              onCreate={onCreateKB}
              onRename={onRenameKB}
              onDelete={onDeleteKB}
            />
          </div>

          {/* Divider */}
          <div className="border-t border-slate-200 dark:border-slate-700 mx-3 my-2" />

          {/* Conversation section */}
          <div className="px-3 space-y-2">
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5
                         bg-gradient-to-r from-emerald-500 to-teal-500
                         text-white text-sm font-medium rounded-xl
                         shadow-md shadow-emerald-500/25
                         hover:shadow-lg hover:shadow-emerald-500/30
                         transition-all duration-200 active:scale-[0.98]"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>

            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={searchKeyword}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="搜索会话..."
                className="w-full pl-9 pr-3 py-2 text-sm
                           bg-slate-100 dark:bg-slate-800
                           border border-slate-200 dark:border-slate-700
                           rounded-xl
                           text-slate-700 dark:text-slate-200
                           placeholder-slate-400 dark:placeholder-slate-500
                           focus:outline-none focus:ring-2 focus:ring-primary-500/30
                           focus:border-primary-500/50
                           transition-all duration-200"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 scrollbar-thin">
            <ConversationList
              conversationList={conversationList}
              searchKeyword={searchKeyword}
              onSelectConversation={onSelectConversation}
              currentConversationId={currentConversationId}
              onDeleteConversation={onDeleteConversation}
              onRenameConversation={onRenameConversation}
              onNewChat={onNewChat}
            />
          </div>

          <div className="border-t border-slate-200 dark:border-slate-700 mx-3 my-2" />

          <div className="px-3">
            <button
              onClick={onUpload}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5
                         bg-gradient-to-r from-primary-500 to-primary-600
                         text-white text-sm font-medium rounded-xl
                         shadow-md shadow-primary-500/25
                         hover:shadow-lg hover:shadow-primary-500/30
                         transition-all duration-200 active:scale-[0.98]"
            >
              <Upload className="w-4 h-4" />
              上传文档
            </button>
          </div>

          <div className="flex-1 mt-2 overflow-hidden">
            <DocumentList
              documents={documents}
              loading={loading}
              uploadProgress={uploadProgress}
              onDelete={onDelete}
              onRefresh={onRefresh}
            />
          </div>
        </div>
      </motion.aside>
    </>
  )
}