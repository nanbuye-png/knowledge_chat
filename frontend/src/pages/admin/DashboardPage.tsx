import { motion } from 'framer-motion'
import {
  Users,
  Database,
  FileText,
  MessageSquare,
  Activity,
  Cpu,
  HardDrive,
  Clock,
  Zap,
  Wifi,
  BookOpen,
  TrendingUp,
  Shield,
} from 'lucide-react'
import { useDashboard } from '../../hooks/useDashboard'
import StatCard from '../../components/admin/dashboard/StatCard'
import SystemMetricCard from '../../components/admin/dashboard/SystemMetricCard'

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
}

const itemAnim = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

function InfoRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-700/50 last:border-0">
      <span className="text-sm text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-sm font-medium text-slate-800 dark:text-slate-100">
        {value || 'N/A'}
      </span>
    </div>
  )
}

export default function DashboardPage() {
  const { dashboard, overview, system, loading, error, refresh } = useDashboard({
    refreshInterval: 30000,
    autoRefresh: true,
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-red-500 text-center py-12">
        <p>加载失败: {error}</p>
        <button
          onClick={refresh}
          className="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          重试
        </button>
      </div>
    )
  }

  if (!dashboard || !overview || !system) return null

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="p-6 max-w-7xl mx-auto space-y-8"
    >
      {/* Header */}
      <motion.div variants={itemAnim} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
            Admin Dashboard
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            系统运行状态与核心数据概览 · 每 30 秒自动刷新
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
        >
          <Clock className="w-4 h-4" />
          刷新
        </button>
      </motion.div>

      {/* Key Metrics */}
      <motion.div variants={itemAnim}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary-500" />
          核心指标
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            title="用户总数"
            value={overview.users_count}
            icon={<Users className="w-5 h-5" />}
            color="from-blue-500 to-blue-600"
            bg="bg-blue-50 dark:bg-blue-900/20"
            text="text-blue-600 dark:text-blue-400"
          />
          <StatCard
            title="知识库"
            value={overview.knowledge_bases_count}
            icon={<Database className="w-5 h-5" />}
            color="from-cyan-500 to-cyan-600"
            bg="bg-cyan-50 dark:bg-cyan-900/20"
            text="text-cyan-600 dark:text-cyan-400"
          />
          <StatCard
            title="文档"
            value={overview.documents_count}
            icon={<FileText className="w-5 h-5" />}
            color="from-orange-500 to-orange-600"
            bg="bg-orange-50 dark:bg-orange-900/20"
            text="text-orange-600 dark:text-orange-400"
          />
          <StatCard
            title="对话"
            value={overview.conversations_count}
            icon={<MessageSquare className="w-5 h-5" />}
            color="from-purple-500 to-purple-600"
            bg="bg-purple-50 dark:bg-purple-900/20"
            text="text-purple-600 dark:text-purple-400"
          />
          <StatCard
            title="消息"
            value={overview.messages_count}
            icon={<Activity className="w-5 h-5" />}
            color="from-teal-500 to-teal-600"
            bg="bg-teal-50 dark:bg-teal-900/20"
            text="text-teal-600 dark:text-teal-400"
          />
        </div>
      </motion.div>

      {/* User Stats */}
      <motion.div variants={itemAnim}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-blue-500" />
          用户统计
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard
            title="总用户"
            value={dashboard.users.total}
            icon={<Users className="w-5 h-5" />}
            color="from-blue-500 to-blue-600"
            bg="bg-blue-50 dark:bg-blue-900/20"
            text="text-blue-600 dark:text-blue-400"
          />
          <StatCard
            title="活跃"
            value={dashboard.users.active}
            icon={<Zap className="w-5 h-5" />}
            color="from-green-500 to-green-600"
            bg="bg-green-50 dark:bg-green-900/20"
            text="text-green-600 dark:text-green-400"
          />
          <StatCard
            title="在线"
            value={dashboard.online.online_users}
            icon={<Wifi className="w-5 h-5" />}
            color="from-emerald-500 to-emerald-600"
            bg="bg-emerald-50 dark:bg-emerald-900/20"
            text="text-emerald-600 dark:text-emerald-400"
          />
          <StatCard
            title="ROOT"
            value={dashboard.users.root_count}
            icon={<Shield className="w-5 h-5" />}
            color="from-purple-500 to-purple-600"
            bg="bg-purple-50 dark:bg-purple-900/20"
            text="text-purple-600 dark:text-purple-400"
          />
          <StatCard
            title="管理员"
            value={dashboard.users.admin_count}
            icon={<Users className="w-5 h-5" />}
            color="from-indigo-500 to-indigo-600"
            bg="bg-indigo-50 dark:bg-indigo-900/20"
            text="text-indigo-600 dark:text-indigo-400"
          />
        </div>
      </motion.div>

      {/* Content & Usage */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Content Stats */}
        <motion.div variants={itemAnim} className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-orange-500" />
            内容统计
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard
              title="知识库"
              value={dashboard.knowledge.total}
              icon={<Database className="w-5 h-5" />}
              color="from-cyan-500 to-cyan-600"
              bg="bg-cyan-50 dark:bg-cyan-900/20"
              text="text-cyan-600 dark:text-cyan-400"
            />
            <StatCard
              title="文档"
              value={dashboard.documents.total}
              icon={<FileText className="w-5 h-5" />}
              color="from-orange-500 to-orange-600"
              bg="bg-orange-50 dark:bg-orange-900/20"
              text="text-orange-600 dark:text-orange-400"
            />
            <StatCard
              title="Chunks"
              value={dashboard.chunks.total}
              icon={<Activity className="w-5 h-5" />}
              color="from-rose-500 to-rose-600"
              bg="bg-rose-50 dark:bg-rose-900/20"
              text="text-rose-600 dark:text-rose-400"
            />
            <StatCard
              title="Embeddings"
              value={dashboard.embeddings.total}
              icon={<Zap className="w-5 h-5" />}
              color="from-amber-500 to-amber-600"
              bg="bg-amber-50 dark:bg-amber-900/20"
              text="text-amber-600 dark:text-amber-400"
            />
          </div>
        </motion.div>

        {/* Today Usage */}
        <motion.div variants={itemAnim}>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-teal-500" />
            今日用量
          </h2>
          <div className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 space-y-1">
            <InfoRow label="请求次数" value={String(dashboard.usage.today_requests)} />
            <InfoRow label="Prompt Tokens" value={dashboard.usage.today_prompt_tokens.toLocaleString()} />
            <InfoRow label="Completion Tokens" value={dashboard.usage.today_completion_tokens.toLocaleString()} />
            <InfoRow label="总 Tokens" value={dashboard.usage.today_total_tokens.toLocaleString()} />
            <InfoRow label="估算成本" value={`¥${dashboard.usage.today_cost.toFixed(4)}`} />
          </div>
        </motion.div>
      </div>

      {/* System Monitoring */}
      <motion.div variants={itemAnim}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-red-500" />
          系统监控
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SystemMetricCard
            title="CPU 使用率"
            value={system.cpu_usage}
            unit="%"
            icon={<Cpu className="w-4 h-4" />}
            color="from-blue-500 to-blue-600"
          />
          <SystemMetricCard
            title="内存使用率"
            value={system.memory_usage}
            unit="%"
            icon={<HardDrive className="w-4 h-4" />}
            color="from-green-500 to-green-600"
          />
          <SystemMetricCard
            title="磁盘使用率"
            value={system.disk_usage}
            unit="%"
            icon={<HardDrive className="w-4 h-4" />}
            color="from-orange-500 to-orange-600"
          />
        </div>
      </motion.div>

      {/* Environment Info */}
      <motion.div variants={itemAnim}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-slate-500" />
          环境信息
        </h2>
        <div className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Python 版本</p>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {system.python_version || 'N/A'}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">操作系统</p>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {system.platform || 'N/A'}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">运行时间</p>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {system.uptime || 'N/A'}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">更新时间</p>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {system.timestamp
                  ? new Date(system.timestamp).toLocaleString('zh-CN')
                  : 'N/A'}
              </p>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}