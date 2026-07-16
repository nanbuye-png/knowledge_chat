import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Shield, ShieldAlert, User, ToggleLeft, ToggleRight, Trash2, Wifi, WifiOff } from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { UserListItem, UserOnlineItem } from '../../api/admin'

type Role = 'USER' | 'ADMIN' | 'ROOT'

const ROLE_OPTIONS: Role[] = ['USER', 'ADMIN', 'ROOT']

export default function UserManagement() {
  const [users, setUsers] = useState<UserListItem[]>([])
  const [onlineMap, setOnlineMap] = useState<Record<number, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [userList, onlineList] = await Promise.all([
        adminApi.listUsers(),
        adminApi.listOnlineUsers(),
      ])
      setUsers(userList)
      const map: Record<number, boolean> = {}
      onlineList.forEach(u => { map[u.id] = u.online })
      setOnlineMap(map)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const showMessage = (msg: string) => {
    setActionMsg(msg)
    setTimeout(() => setActionMsg(null), 3000)
  }

  const handleToggleStatus = async (user: UserListItem) => {
    try {
      await adminApi.updateUserStatus(user.id, !user.is_active)
      showMessage(`用户 ${user.username} 已${!user.is_active ? '启用' : '禁用'}`)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const handleChangeRole = async (userId: number, username: string, newRole: string) => {
    try {
      await adminApi.updateUserRole(userId, newRole)
      showMessage(`用户 ${username} 角色已更新为 ${newRole}`)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const handleDelete = async (user: UserListItem) => {
    if (!window.confirm(`确定要删除用户 "${user.username}" 吗？此操作为软删除，可联系开发恢复。`)) {
      return
    }
    try {
      await adminApi.deleteUser(user.id)
      showMessage(`用户 ${user.username} 已被删除`)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const roleBadge = (role: string) => {
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
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          用户管理
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          管理系统所有用户（共 {users.length} 人）
        </p>
      </motion.div>

      {/* Action toast */}
      {actionMsg && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="mb-4 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 text-sm text-primary-700 dark:text-primary-300"
        >
          {actionMsg}
        </motion.div>
      )}

      {/* Users table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">ID</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">用户名</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">邮箱</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">角色</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">在线</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">创建时间</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {users.map((user, i) => (
                <motion.tr
                  key={user.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02 }}
                  className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs font-mono">
                    {user.id}
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">
                    {user.username}
                  </td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                    {user.email || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {roleBadge(user.role)}
                      <select
                        value={user.role}
                        onChange={(e) => handleChangeRole(user.id, user.username, e.target.value)}
                        className="text-xs bg-transparent border border-slate-200 dark:border-slate-600 rounded-lg px-1.5 py-0.5 text-slate-500 dark:text-slate-400 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600"
                      >
                        {ROLE_OPTIONS.map(r => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {user.is_active ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                        正常
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                        禁用
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {onlineMap[user.id] ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                        <Wifi className="w-3 h-3" />
                        在线
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
                        <WifiOff className="w-3 h-3" />
                        离线
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                    {user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '-'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleToggleStatus(user)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                        title={user.is_active ? '禁用' : '启用'}
                      >
                        {user.is_active ? <ToggleRight className="w-4 h-4 text-green-500" /> : <ToggleLeft className="w-4 h-4" />}
                      </button>
                      <button
                        onClick={() => handleDelete(user)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                        title="删除用户"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {users.length === 0 && (
          <div className="text-center py-12 text-slate-400">
            暂无用户数据
          </div>
        )}
      </div>
    </div>
  )
}