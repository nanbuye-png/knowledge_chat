import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Cpu, Server, CheckCircle, XCircle, RefreshCw, Globe } from 'lucide-react'

interface ProviderInfo {
  name: string
  type: string
  status: 'active' | 'inactive'
  base_url: string
  models: number
}

export default function ProviderManagementPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProviders = useCallback(async () => {
    try {
      setError(null)
      // Provider data is derived from config + model registry
      const { listModels } = await import('../../api/models')
      const models = await listModels()
      const map = new Map<string, { models: Set<string>; count: number }>()
      models.forEach(m => {
        const p = m.provider || 'unknown'
        if (!map.has(p)) map.set(p, { models: new Set(), count: 0 })
        map.get(p)!.models.add(m.model_name)
        map.get(p)!.count++
      })
      const items: ProviderInfo[] = Array.from(map.entries()).map(([name, data]) => ({
        name,
        type: name.toLowerCase().includes('embedding') ? 'Embedding' : 'LLM',
        status: 'active' as const,
        base_url: '',
        models: data.count,
      }))
      setProviders(items)
    } catch (err: any) {
      setError(err.message || 'Provider 加载失败')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchProviders() }, [fetchProviders])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchProviders} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Server className="w-6 h-6 text-indigo-500" />AI Providers
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI Provider 管理与状态</p>
        </div>
        <button onClick={fetchProviders}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors">
          <RefreshCw className="w-4 h-4" />刷新
        </button>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {providers.length === 0 ? (
          <div className="col-span-full text-center py-16 text-slate-400">
            <Server className="w-12 h-12 mx-auto mb-3 text-slate-300" />
            <p>暂无 Provider 数据</p>
          </div>
        ) : (
          providers.map((p, i) => (
            <motion.div key={p.name} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
              className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 text-white shadow-lg">
                    <Globe className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-800 dark:text-slate-200">{p.name}</h3>
                    <span className="text-xs text-slate-400">{p.type}</span>
                  </div>
                </div>
                {p.status === 'active'
                  ? <span className="inline-flex items-center gap-1 text-xs text-green-600"><CheckCircle className="w-3.5 h-3.5" />Active</span>
                  : <span className="inline-flex items-center gap-1 text-xs text-slate-400"><XCircle className="w-3.5 h-3.5" />Inactive</span>
                }
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500">注册模型</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">{p.models}</span>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  )
}