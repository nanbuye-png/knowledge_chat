import { useEffect, useState } from 'react'
import { BarChart3, Cpu, Database, Clock } from 'lucide-react'
import StatCard from '../../components/dashboard/StatCard'
import LoadingState from '../../components/common/LoadingState'
import { getUsageStats, type UsageStats } from '../../api/usage'

export default function UsagePage() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getUsageStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState text="加载用量数据..." />

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-3">
        <BarChart3 className="w-6 h-6 text-emerald-500" />
        用量监控
      </h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="总调用次数" value={stats?.total_calls ?? '--'} icon={Cpu} color="text-blue-500" bgColor="bg-blue-50 dark:bg-blue-900/20" delay={0} />
        <StatCard label="总 Token 消耗" value={stats ? (stats.total_tokens / 1000).toFixed(1) + 'K' : '--'} icon={Database} color="text-purple-500" bgColor="bg-purple-50 dark:bg-purple-900/20" delay={0.05} />
        <StatCard label="平均延迟" value={stats ? stats.avg_latency_ms + 'ms' : '--'} icon={Clock} color="text-orange-500" bgColor="bg-orange-50 dark:bg-orange-900/20" delay={0.1} />
      </div>
    </div>
  )
}