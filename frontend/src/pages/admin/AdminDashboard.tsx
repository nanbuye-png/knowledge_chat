import { motion } from 'framer-motion'
import { Users, Database, FileText, MessageSquare, Activity, Cpu, HardDrive, Clock } from 'lucide-react'
import { useDashboard } from '../../hooks/useDashboard'
import StatCard from '../../components/admin/dashboard/StatCard'
import SystemMetricCard from '../../components/admin/dashboard/SystemMetricCard'
import EnvironmentPanel from '../../components/admin/dashboard/EnvironmentPanel'

export default function AdminDashboard() {
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
          className="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
        >
          重试
        </button>
      </div>
    )
  }

  if (!dashboard || !overview || !system) return null

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          系统概览
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          系统运行状态与统计信息 · 每 30 秒自动刷新
        </p>
      </motion.div>

      {/* Overview Stats */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
          📊 Dashboard Overview
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            title="Users"
            value={overview.users_count}
            icon={<Users className="w-5 h-5" />}
            color="from-blue-500 to-blue-600"
            bg="bg-blue-50 dark:bg-blue-900/20"
            text="text-blue-600 dark:text-blue-400"
            delay={0}
          />
          <StatCard
            title="Knowledge Bases"
            value={overview.knowledge_bases_count}
            icon={<Database className="w-5 h-5" />}
            color="from-cyan-500 to-cyan-600"
            bg="bg-cyan-50 dark:bg-cyan-900/20"
            text="text-cyan-600 dark:text-cyan-400"
            delay={50}
          />
          <StatCard
            title="Documents"
            value={overview.documents_count}
            icon={<FileText className="w-5 h-5" />}
            color="from-orange-500 to-orange-600"
            bg="bg-orange-50 dark:bg-orange-900/20"
            text="text-orange-600 dark:text-orange-400"
            delay={100}
          />
          <StatCard
            title="Conversations"
            value={overview.conversations_count}
            icon={<MessageSquare className="w-5 h-5" />}
            color="from-purple-500 to-purple-600"
            bg="bg-purple-50 dark:bg-purple-900/20"
            text="text-purple-600 dark:text-purple-400"
            delay={150}
          />
          <StatCard
            title="Messages"
            value={overview.messages_count}
            icon={<Activity className="w-5 h-5" />}
            color="from-teal-500 to-teal-600"
            bg="bg-teal-50 dark:bg-teal-900/20"
            text="text-teal-600 dark:text-teal-400"
            delay={200}
          />
        </div>
      </motion.div>

      {/* User Stats */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-8"
      >
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
          👥 用户统计
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            title="用户总数"
            value={dashboard.users.total}
            icon={<Users className="w-5 h-5" />}
            color="from-blue-500 to-blue-600"
            bg="bg-blue-50 dark:bg-blue-900/20"
            text="text-blue-600 dark:text-blue-400"
            delay={0}
          />
          <StatCard
            title="活跃用户"
            value={dashboard.users.active}
            icon={<Users className="w-5 h-5" />}
            color="from-green-500 to-green-600"
            bg="bg-green-50 dark:bg-green-900/20"
            text="text-green-600 dark:text-green-400"
            delay={50}
          />
          <StatCard
            title="已禁用"
            value={dashboard.users.disabled}
            icon={<Users className="w-5 h-5" />}
            color="from-red-500 to-red-600"
            bg="bg-red-50 dark:bg-red-900/20"
            text="text-red-600 dark:text-red-400"
            delay={100}
          />
          <StatCard
            title="ROOT 用户"
            value={dashboard.users.root_count}
            icon={<Users className="w-5 h-5" />}
            color="from-purple-500 to-purple-600"
            bg="bg-purple-50 dark:bg-purple-900/20"
            text="text-purple-600 dark:text-purple-400"
            delay={150}
          />
          <StatCard
            title="管理员"
            value={dashboard.users.admin_count}
            icon={<Users className="w-5 h-5" />}
            color="from-indigo-500 to-indigo-600"
            bg="bg-indigo-50 dark:bg-indigo-900/20"
            text="text-indigo-600 dark:text-indigo-400"
            delay={200}
          />
        </div>
      </motion.div>

      {/* System Monitoring */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="mb-8"
      >
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
          💻 系统监控
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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
            icon={<Cpu className="w-4 h-4" />}
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
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <EnvironmentPanel system={system} />
      </motion.div>
    </div>
  )
}