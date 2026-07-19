import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Activity, Cpu, HardDrive, Clock, Hash, Zap, BarChart3, Database, Server, Wifi, RefreshCw } from 'lucide-react'
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

function ProgressBar({ value, max, label }: { value: number | null; label: string; max?: number }) {
  const pct = value != null ? Math.min(100, value) : 0
  return (
    <div className="p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</p>
        <span className="text-xs text-slate-500">{value != null ? `${value.toFixed(1)}%` : 'N/A'}</span>
      </div>
      <div className="w-full h-2.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-500' : 'bg-primary-500'}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ServiceBadge({ label, status }: { label: string; status: 'healthy' | 'degraded' | 'unavailable' }) {
  return (
    <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-700/50">
      <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
      {status === 'healthy' ? (
        <span className="inline-flex items-center gap-1 text-xs text-green-600"><span className="w-1.5 h-1.5 rounded-full bg-green-500" />Healthy</span>
      ) : status === 'degraded' ? (
        <span className="inline-flex items-center gap-1 text-xs text-amber-600"><span className="w-1.5 h-1.5 rounded-full bg-amber-500" />Degraded</span>
      ) : (
        <span className="inline-flex items-center gap-1 text-xs text-red-600"><span className="w-1.5 h-1.5 rounded-full bg-red-500" />Unavailable</span>
      )}
    </div>
  )
}

export default function MonitoringDashboardPage() {
  const [dashboard, setDashboard] = useState<adminApi.DashboardData | null>(null)
  const [system, setSystem] = useState<adminApi.SystemMonitorStatus | null>(null)
  const [usageStats, setUsageStats] = useState<usageApi.UsageStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [d, s, u] = await Promise.all([
        adminApi.getDashboard(),
        adminApi.getSystemMonitorStatus(),
        usageApi.getUsageStats().catch(() => null),
      ])
      setDashboard(d)
      setSystem(s)
      setUsageStats(u)
    } catch (err: any) { setError(err.message || '监控数据加载失败') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchData} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  if (!dashboard || !system) return null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-cyan-500" />Monitoring Dashboard
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">系统监控与 AI 可观测性</p>
        </div>
        <button onClick={fetchData} className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600"><RefreshCw className="w-4 h-4" />刷新</button>
      </motion.div>

      {/* System Health */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2"><Cpu className="w-5 h-5 text-blue-500" />System Health</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <ProgressBar value={system.cpu_usage} label="CPU Usage" />
          <ProgressBar value={system.memory_usage} label="Memory Usage" />
          <ProgressBar value={system.disk_usage} label="Disk Usage" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard title="Runtime" value={system.uptime || '-'} icon={<Clock className="w-5 h-5" />} color="from-slate-500 to-slate-600" />
          <StatCard title="Python" value={system.python_version?.replace('Python ', '') || '-'} icon={<Cpu className="w-5 h-5" />} color="from-blue-500 to-blue-600" />
          <StatCard title="Platform" value={system.platform?.split(' ')[0] || '-'} icon={<Server className="w-5 h-5" />} color="from-indigo-500 to-indigo-600" />
          <StatCard title="Total Users" value={dashboard.users.total} icon={<Activity className="w-5 h-5" />} color="from-purple-500 to-purple-600" />
        </div>
      </motion.div>

      {/* AI Health */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2"><Activity className="w-5 h-5 text-cyan-500" />AI Health (Today)</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard title="Requests" value={dashboard.usage.today_requests} icon={<Hash className="w-5 h-5" />} color="from-blue-500 to-blue-600" />
          <StatCard title="Prompt Tokens" value={dashboard.usage.today_prompt_tokens.toLocaleString()} icon={<FileTextIcon />} color="from-cyan-500 to-cyan-600" />
          <StatCard title="Completion" value={dashboard.usage.today_completion_tokens.toLocaleString()} icon={<Zap className="w-5 h-5" />} color="from-orange-500 to-orange-600" />
          <StatCard title="Total Tokens" value={dashboard.usage.today_total_tokens.toLocaleString()} icon={<Activity className="w-5 h-5" />} color="from-purple-500 to-purple-600" />
          <StatCard title="Cost" value={`¥${dashboard.usage.today_cost.toFixed(4)}`} icon={<DollarSignIcon />} color="from-emerald-500 to-emerald-600" />
        </div>
        {usageStats && (
          <div className="mt-4 grid grid-cols-3 gap-4">
            <StatCard title="Total Calls (All Time)" value={usageStats.total_calls} icon={<Hash className="w-5 h-5" />} color="from-blue-500 to-blue-600" subtitle="当前用户" />
            <StatCard title="Total Tokens" value={usageStats.total_tokens.toLocaleString()} icon={<Activity className="w-5 h-5" />} color="from-purple-500 to-purple-600" subtitle="当前用户" />
            <StatCard title="Avg Latency" value={`${usageStats.avg_latency_ms}ms`} icon={<Clock className="w-5 h-5" />} color="from-amber-500 to-amber-600" subtitle="当前用户" />
          </div>
        )}
      </motion.div>

      {/* Service Status */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2"><Server className="w-5 h-5 text-green-500" />Service Status</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <ServiceBadge label="Backend API" status="healthy" />
          <ServiceBadge label="SQLite Database" status="healthy" />
          <ServiceBadge label="Vector Store" status={dashboard.embeddings.available ? 'healthy' : 'degraded'} />
          <ServiceBadge label="Cache (Redis)" status="degraded" />
        </div>
      </motion.div>
    </div>
  )
}

function FileTextIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /></svg> }
function DollarSignIcon() { return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg> }