import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Shield, ShieldAlert, Lock, Unlock, Key, FileText, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import * as adminApi from '../../api/admin'

export default function SecurityDashboardPage() {
  const [dashboard, setDashboard] = useState<adminApi.DashboardData | null>(null)
  const [users, setUsers] = useState<adminApi.UserListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [dashData, userList] = await Promise.all([
        adminApi.getDashboard(),
        adminApi.listUsers(),
      ])
      setDashboard(dashData)
      setUsers(userList)
    } catch (err: any) { setError(err.message || '安全数据加载失败') }
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

  if (!dashboard) return null

  // Derived metrics
  const totalUsers = dashboard.users.total
  const activeUsers = dashboard.users.active
  const disabledUsers = dashboard.users.disabled
  const lockedUsers = users.filter(u => u.locked_until && new Date(u.locked_until) > new Date()).length
  const disabledPercentage = totalUsers > 0 ? ((disabledUsers / totalUsers) * 100).toFixed(1) : '0.0'

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

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Shield className="w-6 h-6 text-red-500" />Security Dashboard
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">安全状态总览与风险监控</p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard title="总用户" value={totalUsers} icon={<UsersIcon />} color="from-blue-500 to-blue-600" />
        <StatCard title="活跃用户" value={activeUsers} icon={<CheckCircle className="w-5 h-5" />} color="from-green-500 to-green-600" />
        <StatCard title="已禁用" value={disabledUsers} icon={<XCircle className="w-5 h-5" />} color="from-red-500 to-red-600" subtitle={`${disabledPercentage}% 禁用率`} />
        <StatCard title="锁定用户" value={lockedUsers} icon={<Lock className="w-5 h-5" />} color="from-amber-500 to-amber-600" />
        <StatCard title="禁用率" value={`${disabledPercentage}%`} icon={<AlertTriangle className="w-5 h-5" />} color="from-orange-500 to-orange-600" />
        <StatCard title="系统 ROOT" value={dashboard.users.root_count} icon={<ShieldAlert className="w-5 h-5" />} color="from-purple-500 to-purple-600" />
      </motion.div>

      {/* Account Security Table */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-red-500" />账号安全状态
        </h2>
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">用户</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">角色</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">状态</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">失败次数</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">锁定至</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">最后登录</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">最后活动</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                {users.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-12 text-slate-400">暂无用户数据</td></tr>
                ) : (
                  users.map((u, i) => {
                    const locked = u.locked_until && new Date(u.locked_until) > new Date()
                    return (
                      <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                        <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">{u.username}</td>
                        <td className="px-4 py-3">{roleBadge(u.role)}</td>
                        <td className="px-4 py-3">
                          {!u.is_active ? <span className="text-xs text-red-600">禁用</span>
                            : locked ? <span className="text-xs text-amber-600">锁定</span>
                            : <span className="text-xs text-green-600">正常</span>}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-600">{u.failed_login_count}</td>
                        <td className="px-4 py-3 text-xs text-slate-500">{locked ? new Date(u.locked_until!).toLocaleString('zh-CN') : '-'}</td>
                        <td className="px-4 py-3 text-xs text-slate-500">{u.last_login_at ? new Date(u.last_login_at).toLocaleString('zh-CN') : '-'}</td>
                        <td className="px-4 py-3 text-xs text-slate-500">{u.last_activity_at ? formatRelative(u.last_activity_at) : '-'}</td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

function roleBadge(role: string) {
  if (role === 'ROOT') return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">ROOT</span>
  if (role === 'ADMIN') return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">ADMIN</span>
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">USER</span>
}

function formatRelative(d: string) {
  const diff = Date.now() - new Date(d).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour}小时前`
  return `${Math.floor(hour / 24)}天前`
}

function UsersIcon() {
  return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></svg>
}