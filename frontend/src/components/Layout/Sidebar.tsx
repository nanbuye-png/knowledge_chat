import { motion } from 'framer-motion'
import { Upload, Search, Plus } from 'lucide-react'
import type { Document, UploadProgress, Conversation } from '../../types'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import DocumentList from '../Documents/DocumentList'
import KnowledgeBaseList from '../KnowledgeBase/KnowledgeBaseList'
import ConversationList from '../Conversation/ConversationList'

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
}: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onRefresh} // Just a close handler target
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-30 lg:hidden"
        />
      )}

      {/* Sidebar */}
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
          {/* Knowledge Base section */}
          <div className="px-3 pt-3">
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

          {/* Conversation section: New Chat + Search box */}
          <div className="px-3 space-y-2">
            {/* New Chat button */}
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

            {/* Search box */}
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

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-3 scrollbar-thin">
            <ConversationList
              conversationList={conversationList}
              searchKeyword={searchKeyword}
            />
          </div>

          {/* Divider */}
          <div className="border-t border-slate-200 dark:border-slate-700 mx-3 my-2" />

          {/* Upload button */}
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

          {/* Document list */}
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