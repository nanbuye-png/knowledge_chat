import { motion } from 'framer-motion'
import { FileText, Hash, Star, ExternalLink, Eye } from 'lucide-react'
import type { Citation } from '../../types'

interface Props {
  citations: Citation[]
}

export default function CitationCard({ citations }: Props) {
  if (!citations || citations.length === 0) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700"
    >
      <div className="flex items-center gap-2 mb-2">
        <FileText className="w-3.5 h-3.5 text-primary-500" />
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          引用来源 ({citations.length})
        </span>
      </div>
      <div className="space-y-1.5">
        {citations.map((c, idx) => (
          <motion.div
            key={`${c.document_id}-${c.chunk_id}`}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.05 }}
            className="group flex items-center gap-2 px-2.5 py-2 bg-slate-50 dark:bg-slate-800/50 
                       rounded-lg text-xs hover:bg-slate-100 dark:hover:bg-slate-700/50 
                       transition-colors cursor-pointer border border-slate-200/50 dark:border-slate-700/50"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-slate-600 dark:text-slate-300 truncate font-medium">
                  {c.filename}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-0.5 text-slate-400 dark:text-slate-500">
                <span className="flex items-center gap-1">
                  <Hash className="w-3 h-3" />
                  Chunk {c.chunk_id}
                </span>
                <span className="flex items-center gap-1">
                  <Star className="w-3 h-3 text-amber-400" />
                  {(c.score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-400 hover:text-primary-500">
                <Eye className="w-3.5 h-3.5" />
              </button>
              <button className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-400 hover:text-primary-500">
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}