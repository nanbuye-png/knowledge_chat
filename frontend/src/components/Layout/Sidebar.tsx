import { motion } from 'framer-motion'
import { Upload } from 'lucide-react'
import type { Document, UploadProgress } from '../../types'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import DocumentList from '../Documents/DocumentList'
import KnowledgeBaseList from '../KnowledgeBase/KnowledgeBaseList'

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