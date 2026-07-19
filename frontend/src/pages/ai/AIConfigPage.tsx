import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Cpu, Thermometer, ArrowUpDown, Sliders, Save, RefreshCw } from 'lucide-react'
import * as modelApi from '../../api/models'
import * as promptApi from '../../api/prompts'
import type { LLMModel } from '../../api/models'
import type { PromptTemplate } from '../../api/prompts'

export default function AIConfigPage() {
  const [models, setModels] = useState<LLMModel[]>([])
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchConfig = useCallback(async () => {
    try {
      setError(null)
      const [modelList, promptList] = await Promise.all([
        modelApi.listModels(),
        promptApi.listPrompts(),
      ])
      setModels(modelList.filter(m => m.enabled))
      setPrompts(promptList.filter(p => p.is_active))
    } catch (err: any) {
      setError(err.message || '配置加载失败')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchConfig} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  const activeModel = models[0]?.name || '-'
  const activeModelProvider = models[0]?.provider || '-'
  const activePrompt = prompts[0]?.name || '-'

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Sliders className="w-6 h-6 text-cyan-500" />AI Configuration
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI 运行时配置概览</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="w-5 h-5 text-cyan-500" />
            <h2 className="font-semibold text-slate-800 dark:text-slate-200">默认 LLM</h2>
          </div>
          <p className="text-sm text-slate-500">Provider: <span className="font-medium text-slate-700 dark:text-slate-300">{activeModelProvider}</span></p>
          <p className="text-sm text-slate-500">Model: <span className="font-medium text-slate-700 dark:text-slate-300">{activeModel}</span></p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-2 mb-3">
            <FileTextIcon className="w-5 h-5 text-emerald-500" />
            <h2 className="font-semibold text-slate-800 dark:text-slate-200">默认 Prompt</h2>
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-300">{activePrompt}</p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-2 mb-3">
            <Thermometer className="w-5 h-5 text-orange-500" />
            <h2 className="font-semibold text-slate-800 dark:text-slate-200">Temperature</h2>
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-300">由 Provider 默认控制</p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-2 mb-3">
            <ArrowUpDown className="w-5 h-5 text-purple-500" />
            <h2 className="font-semibold text-slate-800 dark:text-slate-200">Max Tokens</h2>
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-300">由 Provider 默认控制</p>
        </motion.div>
      </div>

      {/* Available Models */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-cyan-500" />可用模型
        </h2>
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">Provider</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">Model</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {models.length === 0 ? (
                <tr><td colSpan={2} className="text-center py-8 text-slate-400">暂无可用模型</td></tr>
              ) : (
                models.map((m, i) => (
                  <tr key={m.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{m.provider}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{m.model_name}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  )
}

function FileTextIcon(props: any) {
  return <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
  </svg>
}