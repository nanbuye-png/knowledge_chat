import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, Users, Building2, Cpu, Settings, Shield, BarChart3, Key, ClipboardList } from 'lucide-react'
import StatCard from '../../components/dashboard/StatCard'
import LoadingState from '../../components/common/LoadingState'
import { getDashboard, type DashboardData } from '../../api/admin'
import { listUsers, type UserListItem } from '../../api/admin'

const modules = [
  { label: '仪表盘', icon: LayoutDashboard, path: '/admin', desc: '平台总览与统计数据', color: 'text-primary-500' },
  { label: '用户管理', icon: Users, path: '/admin/users', desc: '管理系统用户与角色', color: 'text-blue-500' },
  { label: '组织管理', icon: Building2, path: '/organization', desc: '管理组织架构', color: 'text-emerald-500' },
  { label: 'AI 模型', icon: Cpu, path: '/ai/models', desc: 'LLM 与 Embedding 模型配置', color: 'text-purple-500' },
  { label: '系统配置', icon: Settings, path: '/admin/system', desc: '全局系统设置', color: 'text-orange-500' },
  { label: '审计日志', icon: ClipboardList, path: '/admin/audit', desc: '操作审计与日志', color: 'text-rose-500' },
  { label: 'API Keys', icon: Key, path: '/admin/api-keys', desc: 'API 密钥管理', color: 'text-cyan-500' },
  { label: '监控面板', icon: BarChart3, path: '/monitoring', desc: '系统性能监控', color: 'text-indigo-500' },
]

export default function PlatformPage() {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getDashboard(),
    ]).then(([dash]) => {
      setDashboard(dash)
    }).catch(() => {
      setDashboard(null)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div className="p-8 overflow-y-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-3">
          <LayoutDashboard className="w-7 h-7 text-primary-500" />
          Platform Console
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1 ml-10">系统管理空间</p>
      </div>

      {loading ? (
        <LoadingState text="加载平台数据..." />
      ) : (
        <>
          {/* Dashboard Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard label="用户总数" value={dashboard?.users?.total ?? '--'} icon={Users} color="text-blue-500" bgColor="bg-blue-50 dark:bg-blue-900/20" delay={0} />
            <StatCard label="活跃用户" value={dashboard?.users?.active ?? '--'} icon={Users} color="text-emerald-500" bgColor="bg-emerald-50 dark:bg-emerald-900/20" delay={0.05} />
            <StatCard label="知识库" value={dashboard?.knowledge?.total ?? '--'} icon={Building2} color="text-purple-500" bgColor="bg-purple-50 dark:bg-purple-900/20" delay={0.1} />
            <StatCard label="文档" value={dashboard?.documents?.total ?? '--'} icon={ClipboardList} color="text-orange-500" bgColor="bg-orange-50 dark:bg-orange-900/20" delay={0.15} />
            <StatCard label="今日请求" value={dashboard?.usage?.today_requests ?? '--'} icon={BarChart3} color="text-cyan-500" bgColor="bg-cyan-50 dark:bg-cyan-900/20" delay={0.2} />
            <StatCard label="今日 Token" value={dashboard ? (dashboard.usage.today_total_tokens / 1000).toFixed(1) + 'K' : '--'} icon={Cpu} color="text-rose-500" bgColor="bg-rose-50 dark:bg-rose-900/20" delay={0.25} />
          </div>

          {/* Module Grid */}
          <h2 className="text-lg font-semibold text-slate-800 dark:text-white mb-4">管理模块</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {modules.map((mod, i) => (
              <motion.button
                key={mod.path}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.04 }}
                onClick={() => navigate(mod.path)}
                className="text-left p-5 rounded-2xl bg-white dark:bg-slate-800 
                           border border-slate-200 dark:border-slate-700
                           hover:shadow-lg hover:border-primary-300 dark:hover:border-primary-600
                           transition-all duration-200"
              >
                <mod.icon className={`w-7 h-7 ${mod.color} mb-2`} />
                <h3 className="font-semibold text-sm text-slate-800 dark:text-white">{mod.label}</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{mod.desc}</p>
              </motion.button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}