import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { BookOpen, Save, Cpu, Sliders, RefreshCw } from 'lucide-react'
import * as kbApi from '../../api/knowledgeBases'
import * as configApi from '../../api/knowledgeConfig'
import type { KnowledgeBase } from '../../api/knowledgeBases'
import type { KnowledgeConfig } from '../../api/knowledgeConfig'

export default function KnowledgeSettingsPage() {
  const [kbList, setKbList] = useState<KnowledgeBase[]>([])
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null)
  const [config, setConfig] = useState<KnowledgeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Editable fields
  const [chunkSize, setChunkSize] = useState(500)
  const [chunkOverlap, setChunkOverlap] = useState(100)
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [retrievalTopK, setRetrievalTopK] = useState(5)

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(null), 3000)
  }

  const fetchKbList = useCallback(async () => {
    try {
      setError(null)
      const list = await kbApi.listKnowledgeBases()
      setKbList(list)
    } catch (err: any) {
      setError(err.message || '知识库列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchKbList() }, [fetchKbList])

  const loadConfig = useCallback(async (kbId: number) => {
    try {
      setError(null)
      const cfg = await configApi.getKnowledgeConfig(kbId)
      setConfig(cfg)
      setChunkSize(cfg.chunk_size)
      setChunkOverlap(cfg.chunk_overlap)
      setEmbeddingModel(cfg.embedding_model)
      setRetrievalTopK(cfg.retrieval_top_k)
    } catch (err: any) {
      setError(err.message || '配置加载失败')
    }
  }, [])

  const handleSelectKb = async (kb: KnowledgeBase) => {
    setSelectedKb(kb)
    await loadConfig(kb.id)
  }

  const handleSave = async () => {
    if (!selectedKb) return
    try {
      setSaving(true)
      setError(null)
      await configApi.updateKnowledgeConfig(selectedKb.id, {
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        embedding_model: embeddingModel,
        retrieval_top_k: retrievalTopK,
      })
      showSuccess('配置已保存')
      await loadConfig(selectedKb.id)
    } catch (err: any) {
      setError(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Sliders className="w-6 h-6 text-orange-500" />
          知识库设置
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">知识库 AI 参数配置</p>
      </motion.div>

      {/* KB Selector */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">选择知识库</label>
        <div className="relative max-w-md">
          <BookOpen className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <select
            value={selectedKb?.id ?? ''}
            onChange={e => {
              const kb = kbList.find(k => k.id === Number(e.target.value))
              if (kb) handleSelectKb(kb)
            }}
            className="w-full pl-9 pr-8 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/30"
          >
            <option value="">-- 请选择 --</option>
            {kbList.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
        </div>
      </motion.div>

      {/* Messages */}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300">{error}</div>}
      {successMsg && <div className="mb-4 p-3 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-sm text-green-700 dark:text-green-300">{successMsg}</div>}

      {selectedKb ? (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="rounded-2xl p-6 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 space-y-5">
            {/* Chunk Size */}
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Chunk Size</label>
              <p className="text-xs text-slate-400 mb-2">文档分块大小（字符数）</p>
              <input
                type="number" value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))}
                min={100} max={10000} step={100}
                className="w-full max-w-xs px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
            </div>

            {/* Chunk Overlap */}
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Chunk Overlap</label>
              <p className="text-xs text-slate-400 mb-2">分块重叠大小（字符数）</p>
              <input
                type="number" value={chunkOverlap} onChange={e => setChunkOverlap(Number(e.target.value))}
                min={0} max={5000} step={10}
                className="w-full max-w-xs px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
            </div>

            {/* Embedding Model */}
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Embedding Model</label>
              <p className="text-xs text-slate-400 mb-2">嵌入模型标识</p>
              <input
                type="text" value={embeddingModel} onChange={e => setEmbeddingModel(e.target.value)}
                className="w-full max-w-md px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
            </div>

            {/* Retrieval Top K */}
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Retrieval Top K</label>
              <p className="text-xs text-slate-400 mb-2">检索时返回的文档块数量</p>
              <input
                type="number" value={retrievalTopK} onChange={e => setRetrievalTopK(Number(e.target.value))}
                min={1} max={50} step={1}
                className="w-full max-w-xs px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
            </div>

            {/* Save Button */}
            <div className="pt-2">
              <button
                onClick={handleSave} disabled={saving}
                className="flex items-center gap-2 px-6 py-2.5 bg-primary-500 text-white text-sm font-medium rounded-xl hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {saving ? '保存中...' : '保存配置'}
              </button>
            </div>
          </div>
        </motion.div>
      ) : (
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-16 text-center text-slate-400">
          <Sliders className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>请选择一个知识库查看和编辑设置</p>
        </div>
      )}
    </div>
  )
}