import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { BarChart3, Zap, Hash, Activity, Clock, RefreshCw, TrendingUp } from 'lucide-react'
import * as adminApi from '../../api/admin'
import * as usageApi from '../../api/usage'

export default function TokenAnalyticsPage() {
  const [dashboard, setDashboard] = useState<adminApi.DashboardData | null>(null)
  const [records, setRecords] = useState<usageApi.UsageRecord[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([
        adminApi.getDashboard(),
        usageApi.getRecentUsage(200).catch(() => []),
      ])
      setDashboard(d); setRecords(r)
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Daily aggregations
  const dailyMap = new Map<string, { tokens: number; calls: number }>()
  records.forEach(r => {
    const day = new Date(r.created_at).toLocaleDateString('zh-CN')
    const e = dailyMap.get(day) || { tokens: 0, calls: 0 }
    e.tokens += r.total_tokens; e.calls++
    dailyMap.set(day, e)
  })
  const dailyTrend = Array.from(dailyMap.entries()).map(([d, v]) => ({ date: d, ...v })).sort((a, b) => a.date.localeCompare(b.date)).slice(-30)

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>
  if (!dashboard) return null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3"><BarChart3 className="w-6 h-6 text-amber-500" />Token Analytics</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Token 消耗趋势分析</p>
        </div>
        <button onClick={fetchData} className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg"><RefreshCw className="w-4 h-4" />刷新</button>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">今日 Token 统计（全平台）</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border"><div className="flex items-center justify-between mb-3"><div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500 to-cyan-600 text-white shadow-lg"><FileTextIcon /></div><span className="text-3xl font-bold text-slate-800 dark:text-slate-100">{dashboard.usage.today_prompt_tokens.toLocaleString()}</span></div><p className="text-xs font-medium text-cyan-600">Prompt Tokens</p></div>
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border"><div className="flex items-center justify-between mb-3"><div className="p-2 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 text-white shadow-lg"><Zap className="w-5 h-5" /></div><span className="text-3xl font-bold text-slate-800 dark:text-slate-100">{dashboard.usage.today_completion_tokens.toLocaleString()}</span></div><p className="text-xs font-medium text-orange-600">Completion Tokens</p></div>
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border"><div className="flex items-center justify-between mb-3"><div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 text-white shadow-lg"><Activity className="w-5 h-5" /></div><span className="text-3xl font-bold text-slate-800 dark:text-slate-100">{dashboard.usage.today_total_tokens.toLocaleString()}</span></div><p className="text-xs font-medium text-purple-600">Total Tokens</p></div>
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border"><div className="flex items-center justify-between mb-3"><div className="p-2 rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg"><DollarIcon /></div><span className="text-3xl font-bold text-slate-800 dark:text-slate-100">¥{dashboard.usage.today_cost.toFixed(4)}</span></div><p className="text-xs font-medium text-emerald-600">Cost</p></div>
        </div>
      </motion.div>

      {/* Trend */}
      {dailyTrend.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2"><TrendingUp className="w-5 h-5 text-amber-500" />Token Trend (最近 {dailyTrend.length} 天)</h2>
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border">
            <div className="flex items-end gap-2 h-32 mb-2">
              {dailyTrend.map((d, i) => {
                const maxT = Math.max(...dailyTrend.map(x => x.tokens), 1)
                const pct = (d.tokens / maxT) * 100
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-[10px] text-slate-400">{d.tokens.toLocaleString()}</span>
                    <div className="w-full bg-gradient-to-t from-amber-400 to-amber-500 rounded-t-md" style={{ height: `${Math.max(pct, 2)}%` }} title={`${d.date}: ${d.calls} 次, ${d.tokens.toLocaleString()} tokens`} />
                    <span className="text-[10px] text-slate-500 truncate w-full text-center">{d.date.slice(5)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </motion.div>
      )}

      {dailyTrend.length === 0 && <div className="text-center py-16 text-slate-400"><BarChart3 className="w-12 h-12 mx-auto mb-3 text-slate-300" /><p>暂无 Token 趋势数据</p><p className="text-xs mt-1">调用记录仅包含当前账号数据</p></div>}
    </div>
  )
}

function FileTextIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /></svg> }
function DollarIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg> }