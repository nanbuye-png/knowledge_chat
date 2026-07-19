import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Database, FileText, BarChart3, Activity, HardDrive, Zap, Cpu } from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { DashboardData } from '../../api/admin'

function ProgressBar({ value, max, label, unit }: { value: number; max: number; label: string; unit: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</p>
        <span className="text-xs text-slate-500">{value.toLocaleString()} / {max.toLocaleString()} {unit}</span>
      </div>
      <div className="w-full h-2.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-500' : 'bg-primary-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 mt-1">{pct.toFixed(1)}% 已使用</p>
    </div>
  )
}

function StatCard({ title, value, icon, color }: { title: string; value: number | string; icon: React.ReactNode; color: string }) {
  return (
    <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-xl bg-gradient-to-br ${color} text-white shadow-lg`}>{icon}</div>
        <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">{typeof value === 'number' ? value.toLocaleString() : value}</span>
      </div>
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{title}</p>
    </div>
  )
}

export default function QuotaPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const data = await adminApi.getDashboard()
      setDashboard(data)
    } catch (err: any) {
      setError(err.message || '配额数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-500">
        <p className="mb-4">{error}</p>
        <button onClick={fetchData} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
      </div>
    )
  }

  if (!dashboard) return null

  // Quota limits (hardcoded until backend provides them)
  const QUOTA_LIMITS = {
    documents: 10000,
    knowledgeBases: 500,
    chunks: 500000,
    embeddings: 500000,
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-amber-500" />
          配额管理
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">企业资源配额与使用量监控</p>
      </motion.div>

      {/* Usage Overview */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">使用概览</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard title="知识库" value={dashboard.knowledge.total} icon={<Database className="w-5 h-5" />} color="from-cyan-500 to-cyan-600" />
          <StatCard title="文档" value={dashboard.documents.total} icon={<FileText className="w-5 h-5" />} color="from-orange-500 to-orange-600" />
          <StatCard title="Chunks" value={dashboard.chunks.total} icon={<Activity className="w-5 h-5" />} color="from-rose-500 to-rose-600" />
          <StatCard title="Embeddings" value={dashboard.embeddings.total} icon={<Zap className="w-5 h-5" />} color="from-amber-500 to-amber-600" />
        </div>
      </motion.div>

      {/* Usage vs Limits */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">资源配额</h2>
        <div className="space-y-4">
          <ProgressBar value={dashboard.documents.total} max={QUOTA_LIMITS.documents} label="文档数量" unit="份" />
          <ProgressBar value={dashboard.knowledge.total} max={QUOTA_LIMITS.knowledgeBases} label="知识库数量" unit="个" />
          <ProgressBar value={dashboard.chunks.total} max={QUOTA_LIMITS.chunks} label="Chunks" unit="个" />
          <ProgressBar value={dashboard.embeddings.total} max={QUOTA_LIMITS.embeddings} label="Embeddings" unit="个" />
        </div>
      </motion.div>

      {/* Note */}
      <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-xs text-slate-400 text-center">
        配额限制为系统默认值，如需调整请联系 ROOT 管理员
      </motion.p>
    </div>
  )
}