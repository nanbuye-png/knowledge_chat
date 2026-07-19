import { useState, useEffect, useCallback, useRef } from 'react'
import { motion } from 'framer-motion'
import {
  Wifi,
  WifiOff,
  Users,
  Activity,
  Shield,
  ShieldAlert,
  User,
  Clock,
  RefreshCw,
} from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { UserOnlineItem, UserListItem } from '../../api/admin'

const REFRESH_INTERVAL = 15000 // 15 秒

function roleBadge(role: string) {
  if (role === 'ROOT') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
        <ShieldAlert className="w-3 h-3" />
        ROOT
      </span>
    )
  }
  if (role === 'ADMIN') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
        <Shield className="w-3 h-3" />
        ADMIN
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
      <User className="w-3 h-3" />
      USER
    </span>
  )
}

function formatDateTime(d: string | null | undefined): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatRelativeTime(d: string | null | undefined): string {
  if (!d) return '-'
  const now = Date.now()
  const then = new Date(d).getTime()
  const diffMs = now - then
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 10) return '刚刚'
  if (diffSec < 60) return `${diffSec} 秒前`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  return `${diffDay} 天前`
}

export default function OnlineMonitorPage() {
  const [users, setUsers] = useState<UserListItem[]>([])
  const [onlineList, setOnlineList] = useState<UserOnlineItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdateTime, setLastUpdateTime] = useState<string | null>(null)
  const [isAutoRefresh, setIsAutoRefresh] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [userList, onlineData] = await Promise.all([
        adminApi.listUsers(),
        adminApi.listOnlineUsers(),
      ])
      setUsers(userList)
      setOnlineList(onlineData)
      setLastUpdateTime(new Date().toISOString())
    } catch (err: any) {
      setError(err.message || '在线状态获取失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Auto refresh timer
  useEffect(() => {
    if (isAutoRefresh) {
      timerRef.current = setInterval(fetchData, REFRESH_INTERVAL)
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isAutoRefresh, fetchData])

  const toggleAutoRefresh = () => {
    setIsAutoRefresh(prev => !prev)
  }

  // Derived stats
  const totalUsers = users.length
  const onlineCount = onlineList.filter(u => u.online).length
  const onlineRate = totalUsers > 0 ? ((onlineCount / totalUsers) * 100).toFixed(1) : '0.0'

  const sortedOnlineList = [...onlineList].sort((a, b) => {
    // Online first, then by last_activity_at desc
    if (a.online !== b.online) return a.online ? -1 : 1
    const aTime = a.last_activity_at ? new Date(a.last_activity_at).getTime() : 0
    const bTime = b.last_activity_at ? new Date(b.last_activity_at).getTime() : 0
    return bTime - aTime
  })

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

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6"
      >
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
            在线监控
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            实时查看用户在线状态 · 每 15 秒自动刷新
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Auto refresh toggle */}
          <button
            onClick={toggleAutoRefresh}
            className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors ${
              isAutoRefresh
                ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 border border-green-200 dark:border-green-800'
                : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400 border border-slate-200 dark:border-slate-600'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${isAutoRefresh ? 'animate-spin' : ''}`} />
            {isAutoRefresh ? '自动刷新中' : '已暂停'}
          </button>
          {/* Manual refresh */}
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors border border-slate-200 dark:border-slate-600"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </motion.div>

      {/* Stats Cards */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8"
      >
        <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-green-500 to-green-600 text-white shadow-lg">
              <Wifi className="w-5 h-5" />
            </div>
            <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
              {onlineCount}
            </span>
          </div>
          <p className="text-xs font-medium text-green-600 dark:text-green-400">
            在线用户
          </p>
        </div>

        <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg">
              <Users className="w-5 h-5" />
            </div>
            <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
              {totalUsers}
            </span>
          </div>
          <p className="text-xs font-medium text-blue-600 dark:text-blue-400">
            总用户
          </p>
        </div>

        <div className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500 to-cyan-600 text-white shadow-lg">
              <Activity className="w-5 h-5" />
            </div>
            <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
              {onlineRate}%
            </span>
          </div>
          <p className="text-xs font-medium text-cyan-600 dark:text-cyan-400">
            在线率
          </p>
        </div>
      </motion.div>

      {/* Last update info */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex items-center justify-between mb-4"
      >
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Clock className="w-3.5 h-3.5" />
          最后更新: {lastUpdateTime ? formatDateTime(lastUpdateTime) : '-'}
        </div>
        <span className="text-xs text-slate-400">
          在线用户列表（共 {onlineList.length} 人，在线 {onlineCount} 人）
        </span>
      </motion.div>

      {/* Online Users Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">用户名</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">角色</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">最后活动</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">活跃状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">账号状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {sortedOnlineList.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-16 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <WifiOff className="w-8 h-8 text-slate-300" />
                      <p>当前暂无在线用户</p>
                    </div>
                  </td>
                </tr>
              ) : (
                sortedOnlineList.map((u, i) => (
                  <motion.tr
                    key={u.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.02 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                  >
                    {/* Status indicator */}
                    <td className="px-4 py-3">
                      {u.online ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 font-medium">
                          <span className="relative flex w-2.5 h-2.5">
                            <span className="animate-ping absolute inline-flex w-full h-full rounded-full bg-green-400 opacity-75" />
                            <span className="relative inline-flex w-2.5 h-2.5 rounded-full bg-green-500" />
                          </span>
                          在线
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                          <span className="w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-slate-600" />
                          离线
                        </span>
                      )}
                    </td>

                    {/* Username */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400 font-mono">#{u.id}</span>
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {u.username}
                        </span>
                      </div>
                    </td>

                    {/* Role */}
                    <td className="px-4 py-3">
                      {roleBadge(u.role)}
                    </td>

                    {/* Last activity */}
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {formatDateTime(u.last_activity_at)}
                    </td>

                    {/* Relative time */}
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {u.online && u.last_activity_at
                        ? (
                          <span className="text-green-600 dark:text-green-400">
                            {formatRelativeTime(u.last_activity_at)}
                          </span>
                        )
                        : u.last_activity_at
                          ? formatRelativeTime(u.last_activity_at)
                          : '-'}
                    </td>

                    {/* Account status */}
                    <td className="px-4 py-3 text-xs">
                      {u.is_active ? (
                        <span className="text-green-600 dark:text-green-400">正常</span>
                      ) : (
                        <span className="text-red-600 dark:text-red-400">禁用</span>
                      )}
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  )
}