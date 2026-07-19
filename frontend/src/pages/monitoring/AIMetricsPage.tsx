import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Activity, Hash, Zap, Clock, BarChart3, Cpu, RefreshCw } from 'lucide-react'
import * as adminApi from '../../api/admin'
import * as usageApi from '../../api/usage'

function StatCard({ title, value, icon, color, subtitle }: { title: string; value: string | number; icon: React.ReactNode; color: string; subtitle?: string }) {
  return (
    <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-xl bg-gradient-to-br ${color} text-white shadow-lg`}>{icon}</div>
        <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">{value}</span>
      </div>
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{title}</p>
      {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
    </div>
  )
}

export default function AIMetricsPage() {
  const [dashboard, setDashboard] = useState<adminApi.DashboardData | null>(null)
  const [usageStats, setUsageStats] = useState<usageApi.UsageStats | null>(null)
  const [records, setRecords] = useState<usageApi.UsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [d, u, r] = await Promise.all([
        adminApi.getDashboard(),
        usageApi.getUsageStats().catch(() => null),
        usageApi.getRecentUsage(100).catch(() => []),
      ])
      setDashboard(d)
      setUsageStats(u)
      setRecords(r)
    } catch (err: any) { setError(err.message || 'AI 指标加载失败') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>
  if (error) return <div className="flex flex-col items-center justify-center h-64 text-red-500"><p className="mb-4">{error}</p><button onClick={fetchData} className="px-4 py-2 bg-primary-500 text-white rounded-lg">重新加载</button></div>
  if (!dashboard) return null

  // Model ranking from usage records
  const modelRanking = new Map<string, { calls: number; tokens: number }>()
  records.forEach(r => {
    const key = `${r.provider}/${r.model}`
    const e = modelRanking.get(key) || { calls: 0, tokens: 0 }
    e.calls++; e.tokens += r.total_tokens
    modelRanking.set(key, e)
  })
  const sortedModels = Array.from(modelRanking.entries()).map(([k, v]) => ({ model: k, ...v })).sort((a, b) => b.calls - a.calls).slice(0, 10)

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3"><Activity className="w-6 h-6 text-cyan-500" />AI Metrics</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI 调用指标与模型分析</p>
        </div>
        <button onClick={fetchData} className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg"><RefreshCw className="w-4 h-4" />刷新</button>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">今日统计（全平台）</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard title="Requests" value={dashboard.usage.today_requests} icon={<Hash className="w-5 h-5" />} color="from-blue-500 to-blue-600" />
          <StatCard title="Prompt Tokens" value={dashboard.usage.today_prompt_tokens.toLocaleString()} icon={<FileTextIcon />} color="from-cyan-500 to-cyan-600" />
          <StatCard title="Completion Tokens" value={dashboard.usage.today_completion_tokens.toLocaleString()} icon={<Zap className="w-5 h-5" />} color="from-orange-500 to-orange-600" />
          <StatCard title="Total Tokens" value={dashboard.usage.today_total_tokens.toLocaleString()} icon={<Activity className="w-5 h-5" />} color="from-purple-500 to-purple-600" />
          <StatCard title="Cost" value={`¥${dashboard.usage.today_cost.toFixed(4)}`} icon={<DollarSignIcon />} color="from-emerald-500 to-emerald-600" />
        </div>
      </motion.div>

      {usageStats && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">累计统计（当前用户）</h2>
          <div className="grid grid-cols-3 gap-4">
            <StatCard title="Total Calls" value={usageStats.total_calls} icon={<Hash className="w-5 h-5" />} color="from-blue-500 to-blue-600" />
            <StatCard title="Total Tokens" value={usageStats.total_tokens.toLocaleString()} icon={<Activity className="w-5 h-5" />} color="from-purple-500 to-purple-600" />
            <StatCard title="Avg Latency" value={`${usageStats.avg_latency_ms}ms`} icon={<Clock className="w-5 h-5" />} color="from-amber-500 to-amber-600" />
          </div>
        </motion.div>
      )}

      {sortedModels.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2"><Cpu className="w-5 h-5 text-cyan-500" />Model Ranking</h2>
          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">模型</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">调用次数</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">总 Tokens</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                {sortedModels.map((m, i) => (
                  <tr key={m.model} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">{m.model}</td>
                    <td className="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{m.calls}</td>
                    <td className="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{m.tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {sortedModels.length === 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-16 text-slate-400">
          <Activity className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>暂无调用数据</p>
        </motion.div>
      )}
    </div>
  )
}

function FileTextIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /></svg> }
function DollarSignIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg> }