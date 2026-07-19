import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Hash,
  Zap,
  Clock,
  DollarSign,
  Activity,
  Calendar,
  ChevronDown,
  RefreshCw,
  TrendingUp,
  FileText,
  Cpu,
  BarChart3,
} from 'lucide-react'
import * as adminApi from '../../api/admin'
import * as usageApi from '../../api/usage'
import type { DashboardData, DashboardOverview } from '../../api/admin'
import type { UsageRecord, UsageStats } from '../../api/usage'

type TimeRange = 'today' | '7d' | '30d'

const TIME_RANGE_LABELS: Record<TimeRange, string> = {
  today: '今日',
  '7d': '最近 7 天',
  '30d': '最近 30 天',
}

function formatNumber(n: number | undefined | null): string {
  if (n == null) return '-'
  return n.toLocaleString()
}

function formatCost(cost: number | undefined | null): string {
  if (cost == null) return '-'
  return `¥${cost.toFixed(4)}`
}

function formatDateTime(d: string | null | undefined): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function UsageDashboardPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>('today')
  const [showTimeDropdown, setShowTimeDropdown] = useState(false)

  // Data
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [recentRecords, setRecentRecords] = useState<UsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Auto refresh
  const [isAutoRefresh, setIsAutoRefresh] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      // Dashboard has today's aggregated usage across all users
      const [dashData, overviewData] = await Promise.all([
        adminApi.getDashboard(),
        adminApi.getDashboardOverview(),
      ])
      setDashboard(dashData)
      setOverview(overviewData)

      // Recent usage records (per current admin user)
      const limit = timeRange === 'today' ? 50 : timeRange === '7d' ? 100 : 200
      usageApi.getRecentUsage(limit).then(setRecentRecords).catch(() => {})
    } catch (err: any) {
      setError(err.message || '使用数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  // Initial fetch
  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Auto refresh timer
  useEffect(() => {
    if (isAutoRefresh) {
      timerRef.current = setInterval(fetchData, 30000)
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isAutoRefresh, fetchData])

  // Derived — today usage from dashboard
  const usage = dashboard?.usage

  // Recent records filtered by time range (client-side approximation)
  const filteredRecords = useMemo(() => {
    if (!recentRecords.length) return []
    const now = Date.now()
    const cutoffMap: Record<TimeRange, number> = {
      today: now - 24 * 60 * 60 * 1000,
      '7d': now - 7 * 24 * 60 * 60 * 1000,
      '30d': now - 30 * 24 * 60 * 60 * 1000,
    }
    const cutoff = cutoffMap[timeRange]
    return recentRecords.filter(r => new Date(r.created_at).getTime() > cutoff)
  }, [recentRecords, timeRange])

  // Aggregate filtered records for stats
  const filteredStats = useMemo(() => {
    if (!filteredRecords.length) return null
    return {
      total_calls: filteredRecords.length,
      total_prompt_tokens: filteredRecords.reduce((s, r) => s + r.prompt_tokens, 0),
      total_completion_tokens: filteredRecords.reduce((s, r) => s + r.completion_tokens, 0),
      total_tokens: filteredRecords.reduce((s, r) => s + r.total_tokens, 0),
    }
  }, [filteredRecords])

  // Model aggregation
  const modelStats = useMemo(() => {
    const map = new Map<string, { calls: number; tokens: number }>()
    filteredRecords.forEach(r => {
      const key = `${r.provider}/${r.model}`
      const existing = map.get(key) || { calls: 0, tokens: 0 }
      existing.calls += 1
      existing.tokens += r.total_tokens
      map.set(key, existing)
    })
    return Array.from(map.entries())
      .map(([model, stats]) => ({ model, ...stats }))
      .sort((a, b) => b.calls - a.calls)
      .slice(0, 10)
  }, [filteredRecords])

  // Daily aggregation for trend
  const dailyTrend = useMemo(() => {
    const map = new Map<string, { calls: number; tokens: number }>()
    filteredRecords.forEach(r => {
      const day = new Date(r.created_at).toLocaleDateString('zh-CN')
      const existing = map.get(day) || { calls: 0, tokens: 0 }
      existing.calls += 1
      existing.tokens += r.total_tokens
      map.set(day, existing)
    })
    return Array.from(map.entries())
      .map(([date, stats]) => ({ date, ...stats }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [filteredRecords])

  // ---------- Render ----------

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-500">
        <p className="mb-4">{error}</p>
        <button
          onClick={fetchData}
          className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          重新加载
        </button>
      </div>
    )
  }

  if (!dashboard) return null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
            使用分析
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            LLM 调用使用统计与趋势分析
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Time Range Selector */}
          <div className="relative">
            <button
              onClick={() => setShowTimeDropdown(!showTimeDropdown)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg border border-slate-200 dark:border-slate-600 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              <Calendar className="w-4 h-4" />
              {TIME_RANGE_LABELS[timeRange]}
              <ChevronDown className="w-3 h-3" />
            </button>
            {showTimeDropdown && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowTimeDropdown(false)} />
                <div className="absolute right-0 mt-1 z-20 w-36 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden">
                  {(Object.entries(TIME_RANGE_LABELS) as [TimeRange, string][]).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={() => { setTimeRange(key); setShowTimeDropdown(false) }}
                      className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                        timeRange === key
                          ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400'
                          : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Auto refresh toggle */}
          <button
            onClick={() => setIsAutoRefresh(!isAutoRefresh)}
            className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors border ${
              isAutoRefresh
                ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 border-green-200 dark:border-green-800'
                : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400 border-slate-200 dark:border-slate-600'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${isAutoRefresh ? 'animate-spin' : ''}`} />
            {isAutoRefresh ? '自动刷新' : '已暂停'}
          </button>
        </div>
      </motion.div>

      {/* Core Metrics — from admin dashboard (all users, today) */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary-500" />
          今日总览（全平台）
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg">
                <Hash className="w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatNumber(usage?.today_requests)}
              </span>
            </div>
            <p className="text-xs font-medium text-blue-600 dark:text-blue-400">调用次数</p>
          </div>

          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500 to-cyan-600 text-white shadow-lg">
                <FileText className="w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatNumber(usage?.today_prompt_tokens)}
              </span>
            </div>
            <p className="text-xs font-medium text-cyan-600 dark:text-cyan-400">Prompt Tokens</p>
          </div>

          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 text-white shadow-lg">
                <Zap className="w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatNumber(usage?.today_completion_tokens)}
              </span>
            </div>
            <p className="text-xs font-medium text-orange-600 dark:text-orange-400">Completion Tokens</p>
          </div>

          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 text-white shadow-lg">
                <Activity className="w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatNumber(usage?.today_total_tokens)}
              </span>
            </div>
            <p className="text-xs font-medium text-purple-600 dark:text-purple-400">总 Tokens</p>
          </div>

          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg">
                <DollarSign className="w-5 h-5" />
              </div>
              <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatCost(usage?.today_cost)}
              </span>
            </div>
            <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400">费用</p>
          </div>
        </div>
      </motion.div>

      {/* Daily Trend — bar chart (simple bars) */}
      {dailyTrend.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
        >
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-500" />
            调用趋势
          </h2>
          <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <div className="flex items-end gap-2 h-32 mb-2">
              {dailyTrend.map((day, i) => {
                const maxTokens = Math.max(...dailyTrend.map(d => d.tokens), 1)
                const heightPct = (day.tokens / maxTokens) * 100
                return (
                  <div
                    key={day.date}
                    className="flex-1 flex flex-col items-center gap-1"
                  >
                    <span className="text-[10px] text-slate-400">{day.calls}</span>
                    <div
                      className="w-full bg-gradient-to-t from-primary-400 to-primary-500 rounded-t-md transition-all"
                      style={{ height: `${Math.max(heightPct, 2)}%` }}
                      title={`${day.date}: ${day.calls} 次, ${day.tokens.toLocaleString()} tokens`}
                    />
                    <span className="text-[10px] text-slate-500 truncate w-full text-center">
                      {day.date.slice(5)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </motion.div>
      )}

      {/* Model Ranking */}
      {modelStats.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-cyan-500" />
            模型排行
          </h2>
          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                  <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">模型</th>
                  <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">调用次数</th>
                  <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">总 Tokens</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                {modelStats.map((m, i) => (
                  <tr key={m.model} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
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

      {/* Recent Usage Records */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-slate-500" />
          最近调用记录
        </h2>
        {filteredRecords.length === 0 ? (
          <div className="rounded-2xl p-10 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
            <p className="text-center text-slate-400">暂无使用数据</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                    <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Provider</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Model</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Prompt</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Completion</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Total</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">Latency</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">时间</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                  {filteredRecords.slice(0, 50).map((r, i) => (
                    <motion.tr
                      key={r.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.005 }}
                      className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-300">{r.provider}</td>
                      <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">{r.model}</td>
                      <td className="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{r.prompt_tokens.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{r.completion_tokens.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-medium text-slate-700 dark:text-slate-200">{r.total_tokens.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-slate-500 dark:text-slate-400 text-xs">{r.latency_ms.toFixed(0)}ms</td>
                      <td className="px-4 py-3 text-right text-slate-400 text-xs whitespace-nowrap">{formatDateTime(r.created_at)}</td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </motion.div>

      {/* Note about data scope */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-xs text-slate-400 text-center"
      >
        全平台统计数据来自系统 Dashboard · 调用记录为当前账号数据
      </motion.div>
    </div>
  )
}