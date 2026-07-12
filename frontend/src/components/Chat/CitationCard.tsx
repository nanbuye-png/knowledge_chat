import { motion } from 'framer-motion'
import { FileText, Hash, Star } from 'lucide-react'
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
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
        引用来源 (Citations)：
      </p>
      <div className="flex flex-wrap gap-2">
        {citations.map((c, idx) => (
          <motion.div
            key={`${c.document_id}-${c.chunk_id}`}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.05 }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs"
          >
            <FileText className="w-3 h-3 text-primary-500" />
            <span className="text-slate-600 dark:text-slate-300 truncate max-w-[120px]">{c.filename}</span>
            <span className="text-slate-400"><Hash className="w-2.5 h-2.5 inline" />{c.chunk_id}</span>
            <span className="text-amber-500"><Star className="w-2.5 h-2.5 inline" />{c.score.toFixed(2)}</span>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}