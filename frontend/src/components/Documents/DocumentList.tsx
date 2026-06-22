import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Upload, RefreshCw, X, Inbox } from 'lucide-react'
import type { Document, UploadProgress } from '../../types'
import DocumentItem from './DocumentItem'

interface DocumentListProps {
  documents: Document[]
  loading: boolean
  uploadProgress: UploadProgress | null
  onDelete: (id: string) => void
  onRefresh: () => void
}

export default function DocumentList({ documents, loading, uploadProgress, onDelete, onRefresh }: DocumentListProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary-500" />
          文档列表
        </h3>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 
                     hover:bg-primary-50 dark:hover:bg-primary-900/30
                     transition-colors duration-200"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Upload progress */}
      <AnimatePresence>
        {uploadProgress && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mx-3 mt-2 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-100 dark:border-primary-800"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-primary-700 dark:text-primary-300 truncate max-w-[150px]">
                {uploadProgress.filename}
              </span>
              <span className="text-xs text-primary-500">
                {uploadProgress.status === 'uploading' ? '上传中...' :
                 uploadProgress.status === 'processing' ? '处理中...' : ''}
              </span>
            </div>
            <div className="w-full h-1.5 bg-primary-200 dark:bg-primary-800 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-primary-500 to-primary-600 rounded-full"
                initial={{ width: '0%' }}
                animate={{
                  width: uploadProgress.status === 'completed' ? '100%' :
                         uploadProgress.status === 'failed' ? '100%' : '60%',
                }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-2 space-y-1">
        <AnimatePresence mode="popLayout">
          {documents.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center py-12 text-slate-400"
            >
              <Inbox className="w-12 h-12 mb-3 text-slate-300 dark:text-slate-600" />
              <p className="text-sm">暂无文档</p>
              <p className="text-xs mt-1">上传文档开始构建知识库</p>
            </motion.div>
          ) : (
            documents.map((doc) => (
              <DocumentItem key={doc.id} document={doc} onDelete={onDelete} />
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-slate-200 dark:border-slate-700">
        <p className="text-xs text-slate-400 text-center">
          共 {documents.length} 个文档
        </p>
      </div>
    </div>
  )
}