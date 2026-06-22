import { motion } from 'framer-motion'
import { FileText, File, Trash2, CheckCircle, Clock, AlertCircle, X } from 'lucide-react'
import type { Document } from '../../types'

interface DocumentItemProps {
  document: Document
  onDelete: (id: string) => void
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const hours = Math.floor(diff / (1000 * 60 * 60))
  
  if (hours < 1) return '刚刚'
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN')
}

function getFileIcon(type: string) {
  switch (type) {
    case '.pdf': return <FileText className="w-4 h-4 text-red-500" />
    case '.docx':
    case '.doc': return <FileText className="w-4 h-4 text-blue-500" />
    case '.md': return <FileText className="w-4 h-4 text-purple-500" />
    default: return <File className="w-4 h-4 text-slate-500" />
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed': return <CheckCircle className="w-3.5 h-3.5 text-green-500" />
    case 'processing': return <Clock className="w-3.5 h-3.5 text-amber-500" />
    case 'failed': return <AlertCircle className="w-3.5 h-3.5 text-red-500" />
    default: return null
  }
}

function getStatusText(status: string) {
  switch (status) {
    case 'completed': return '已完成'
    case 'processing': return '处理中'
    case 'failed': return '失败'
    default: return status
  }
}

export default function DocumentItem({ document, onDelete }: DocumentItemProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20, height: 0 }}
      className="group flex items-center gap-3 px-3 py-2.5 rounded-xl
                 hover:bg-slate-100 dark:hover:bg-slate-700/50
                 transition-all duration-200 cursor-pointer"
    >
      {/* File icon */}
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-700 
                      flex items-center justify-center">
        {getFileIcon(document.file_type)}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
          {document.filename}
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          <div className="flex items-center gap-1">
            {getStatusIcon(document.status)}
            <span className={`text-xs ${
              document.status === 'completed' ? 'text-green-600 dark:text-green-400' :
              document.status === 'processing' ? 'text-amber-600 dark:text-amber-400' :
              document.status === 'failed' ? 'text-red-600 dark:text-red-400' :
              'text-slate-400'
            }`}>
              {getStatusText(document.status)}
            </span>
          </div>
          <span className="text-xs text-slate-400">{formatFileSize(document.file_size)}</span>
          <span className="text-xs text-slate-400">{formatTime(document.created_at)}</span>
        </div>
        {document.status === 'completed' && document.chunk_count > 0 && (
          <p className="text-xs text-slate-400 mt-0.5">
            {document.chunk_count} 个文本块
          </p>
        )}
        {document.status === 'failed' && document.error_message && (
          <p className="text-xs text-red-400 mt-0.5 truncate" title={document.error_message}>
            {document.error_message}
          </p>
        )}
      </div>

      {/* Delete button */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete(document.id)
        }}
        className="flex-shrink-0 p-1.5 rounded-lg opacity-0 group-hover:opacity-100
                   text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30
                   transition-all duration-200"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </motion.div>
  )
}