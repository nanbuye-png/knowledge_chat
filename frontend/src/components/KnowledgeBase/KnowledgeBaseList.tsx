import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { BookOpen, Plus, Pencil, Trash2, X, Check } from 'lucide-react'
import type { KnowledgeBase } from '../../api/knowledgeBases'

interface KnowledgeBaseListProps {
  knowledgeBases: KnowledgeBase[]
  loading: boolean
  selectedId: number | null
  onSelect: (kb: KnowledgeBase) => void
  onCreate: (name: string) => Promise<void>
  onRename: (id: number, name: string) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

export default function KnowledgeBaseList({
  knowledgeBases,
  loading,
  selectedId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: KnowledgeBaseListProps) {
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingName, setEditingName] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)

  const handleCreate = async () => {
    const trimmed = newName.trim()
    if (!trimmed) return
    await onCreate(trimmed)
    setNewName('')
    setShowCreate(false)
  }

  const handleRename = async (id: number) => {
    const trimmed = editingName.trim()
    if (!trimmed) {
      setEditingId(null)
      return
    }
    await onRename(id, trimmed)
    setEditingId(null)
    setEditingName('')
  }

  const handleDelete = async (id: number) => {
    await onDelete(id)
    setDeleteConfirmId(null)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-1.5">
          <BookOpen className="w-4 h-4 text-primary-500" />
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            我的知识库
          </span>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="p-1 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-primary-50 
                     dark:hover:bg-primary-900/20 transition-all duration-200"
          title="新建知识库"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Create input */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-3 pb-2 overflow-hidden"
          >
            <div className="flex gap-1">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate()
                  if (e.key === 'Escape') { setShowCreate(false); setNewName('') }
                }}
                placeholder="知识库名称..."
                autoFocus
                className="flex-1 px-2 py-1 text-xs border border-primary-200 dark:border-primary-700 
                           rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200
                           focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
              <button
                onClick={handleCreate}
                disabled={!newName.trim()}
                className="p-1 rounded-lg text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20
                           disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewName('') }}
                className="p-1 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 scrollbar-thin">
        {loading && knowledgeBases.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-5 h-5 border-2 border-primary-300 border-t-primary-500 rounded-full animate-spin" />
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {knowledgeBases.map((kb) => (
              <motion.div
                key={kb.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className={`group flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition-colors
                           ${kb.id === selectedId
                             ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                             : 'hover:bg-slate-100 dark:hover:bg-slate-800/50'
                           }`}
                onClick={() => onSelect(kb)}
              >
                {editingId === kb.id ? (
                  <>
                    <input
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename(kb.id)
                        if (e.key === 'Escape') { setEditingId(null); setEditingName('') }
                      }}
                      autoFocus
                      className="flex-1 px-2 py-0.5 text-xs border border-primary-200 dark:border-primary-700
                                 rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200
                                 focus:outline-none focus:ring-1 focus:ring-primary-500"
                    />
                    <button
                      onClick={() => handleRename(kb.id)}
                      disabled={!editingName.trim()}
                      className="p-0.5 rounded text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20
                                 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => { setEditingId(null); setEditingName('') }}
                      className="p-0.5 rounded text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="flex-1 text-xs text-slate-700 dark:text-slate-300 truncate">
                      {kb.name}
                    </span>
                    <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditingId(kb.id)
                          setEditingName(kb.name)
                        }}
                        className="p-0.5 rounded text-slate-400 hover:text-primary-500 hover:bg-primary-50 
                                   dark:hover:bg-primary-900/20 transition-all"
                        title="重命名"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteConfirmId(kb.id)
                        }}
                        className="p-0.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 
                                   dark:hover:bg-red-900/20 transition-all"
                        title="删除"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
        {!loading && knowledgeBases.length === 0 && (
          <p className="text-center text-xs text-slate-400 py-4">
            暂无知识库
          </p>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <AnimatePresence>
        {deleteConfirmId !== null && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center"
            onClick={() => setDeleteConfirmId(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-xl mx-3 w-64"
            >
              <p className="text-sm text-slate-700 dark:text-slate-300 mb-1">
                确定要删除该知识库吗？
              </p>
              <p className="text-xs text-slate-400 mb-3">
                此操作不可撤销。
              </p>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setDeleteConfirmId(null)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium
                             text-slate-600 dark:text-slate-300
                             hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={() => handleDelete(deleteConfirmId)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium
                             bg-red-500 text-white hover:bg-red-600 transition-colors"
                >
                  确认删除
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}