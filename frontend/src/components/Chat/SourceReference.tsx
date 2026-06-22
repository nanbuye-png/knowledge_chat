import { motion } from 'framer-motion'
import { FileText } from 'lucide-react'
import type { SourceReference as SourceRef } from '../../types'

interface SourceReferenceProps {
  sources: SourceRef[]
}

export default function SourceReference({ sources }: SourceReferenceProps) {
  if (!sources || sources.length === 0) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700"
    >
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
        来源引用：
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, index) => (
          <motion.div
            key={`${source.document_id}-${source.chunk_index}`}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            className="group relative flex items-center gap-1.5 px-2.5 py-1.5 
                       bg-slate-100 dark:bg-slate-800 rounded-lg text-xs
                       hover:bg-primary-50 dark:hover:bg-primary-900/30
                       transition-colors duration-200 cursor-default"
          >
            <FileText className="w-3 h-3 text-primary-500" />
            <span className="text-slate-600 dark:text-slate-300 truncate max-w-[120px]">
              {source.filename}
            </span>
            <span className="text-slate-400 dark:text-slate-500">
              #{source.chunk_index}
            </span>

            {/* Tooltip */}
            <div className="absolute bottom-full left-0 mb-2 w-64 p-3 
                          bg-white dark:bg-slate-800 rounded-lg shadow-xl border 
                          border-slate-200 dark:border-slate-700 
                          opacity-0 group-hover:opacity-100 
                          transition-opacity duration-200 z-50 pointer-events-none">
              <p className="text-xs text-slate-600 dark:text-slate-300 line-clamp-4">
                {source.text}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}