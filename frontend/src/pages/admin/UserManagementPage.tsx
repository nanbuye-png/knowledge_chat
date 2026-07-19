import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Search,
  Shield,
  ShieldAlert,
  User,
  ToggleLeft,
  ToggleRight,
  Trash2,
  Wifi,
  WifiOff,
  Lock,
  CheckCircle,
  XCircle,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { UserListItem } from '../../api/admin'
import { usePermission } from '../../hooks/usePermission'

type Role = 'USER' | 'ADMIN' | 'ROOT'
type StatusFilter = 'all' | 'active' | 'disabled' | 'locked'

const ROLE_OPTIONS: Role[] = ['USER', 'ADMIN', 'ROOT']

const PAGE_SIZE = 15

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

function isUserLocked(user: UserListItem): boolean {
  return !!user.locked_until && new Date(user.locked_until) > new Date()
}

function statusBadge(user: UserListItem) {
  if (!user.is_active) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
        <XCircle className="w-3.5 h-3.5" />
        禁用
      </span>
    )
  }
  if (isUserLocked(user)) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
        <Lock className="w-3.5 h-3.5" />
        锁定
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
      <CheckCircle className="w-3.5 h-3.5" />
      正常
    </span>
  )
}

export default function UserManagementPage() {
  const { isRoot, isAdmin } = usePermission()

  // Data
  const [users, setUsers] = useState<UserListItem[]>([])
  const [onlineMap, setOnlineMap] = useState<Record<number, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  // Search & filters
  const [searchKeyword, setSearchKeyword] = useState('')
  const [roleFilter, setRoleFilter] = useState<Role | ''>('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Pagination
  const [currentPage, setCurrentPage] = useState(1)

  // Role change modal
  const [roleModal, setRoleModal] = useState<{ user: UserListItem } | null>(null)
  const [selectedNewRole, setSelectedNewRole] = useState<Role>('USER')

  // Delete confirm modal
  const [deleteModal, setDeleteModal] = useState<{ user: UserListItem } | null>(null)

  const showMessage = (msg: string) => {
    setActionMsg(msg)
    setTimeout(() => setActionMsg(null), 3000)
  }

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      setLoading(true)
      const [userList, onlineList] = await Promise.all([
        adminApi.listUsers(),
        adminApi.listOnlineUsers(),
      ])
      setUsers(userList)
      const map: Record<number, boolean> = {}
      onlineList.forEach(u => { map[u.id] = u.online })
      setOnlineMap(map)
    } catch (err: any) {
      setError(err.message || '用户列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [searchKeyword, roleFilter, statusFilter])

  // Filtered + searched
  const filteredUsers = useMemo(() => {
    let list = users

    // Search by username
    if (searchKeyword.trim()) {
      const kw = searchKeyword.trim().toLowerCase()
      list = list.filter(u => u.username.toLowerCase().includes(kw))
    }

    // Role filter
    if (roleFilter) {
      list = list.filter(u => u.role === roleFilter)
    }

    // Status filter
    if (statusFilter === 'active') {
      list = list.filter(u => u.is_active && !isUserLocked(u))
    } else if (statusFilter === 'disabled') {
      list = list.filter(u => !u.is_active)
    } else if (statusFilter === 'locked') {
      list = list.filter(u => u.is_active && isUserLocked(u))
    }

    return list
  }, [users, searchKeyword, roleFilter, statusFilter])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE))
  const safeCurrentPage = Math.min(currentPage, totalPages)
  const paginatedUsers = useMemo(() => {
    const start = (safeCurrentPage - 1) * PAGE_SIZE
    return filteredUsers.slice(start, start + PAGE_SIZE)
  }, [filteredUsers, safeCurrentPage])

  // Actions
  const handleToggleStatus = async (user: UserListItem) => {
    try {
      await adminApi.updateUserStatus(user.id, !user.is_active)
      showMessage(`用户 ${user.username} 已${!user.is_active ? '启用' : '禁用'}`)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const handleChangeRole = async () => {
    if (!roleModal) return
    const { user } = roleModal
    try {
      await adminApi.updateUserRole(user.id, selectedNewRole)
      showMessage(`用户 ${user.username} 角色已更新为 ${selectedNewRole}`)
      setRoleModal(null)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    const { user } = deleteModal
    try {
      await adminApi.deleteUser(user.id)
      showMessage(`用户 ${user.username} 已被删除`)
      setDeleteModal(null)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const openRoleModal = (user: UserListItem) => {
    setSelectedNewRole(user.role as Role)
    setRoleModal({ user })
  }

  const formatDate = (d: string | null | undefined) => {
    if (!d) return '-'
    return new Date(d).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

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
        className="mb-6"
      >
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          用户管理
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          管理系统所有用户 · 共 {users.length} 人
        </p>
      </motion.div>

      {/* Action toast */}
      {actionMsg && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 text-sm text-primary-700 dark:text-primary-300"
        >
          {actionMsg}
        </motion.div>
      )}

      {/* Search & Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6 flex flex-wrap items-center gap-3"
      >
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchKeyword}
            onChange={e => setSearchKeyword(e.target.value)}
            placeholder="搜索用户名..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
          />
        </div>

        {/* Role filter */}
        <div className="relative">
          <SlidersHorizontal className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value as Role | '')}
            className="pl-9 pr-8 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/30"
          >
            <option value="">全部角色</option>
            <option value="ROOT">ROOT</option>
            <option value="ADMIN">ADMIN</option>
            <option value="USER">USER</option>
          </select>
        </div>

        {/* Status filter */}
        <div className="relative">
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as StatusFilter)}
            className="pl-3 pr-8 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/30"
          >
            <option value="all">全部状态</option>
            <option value="active">正常</option>
            <option value="disabled">禁用</option>
            <option value="locked">锁定</option>
          </select>
        </div>

        {/* Counter */}
        <span className="text-sm text-slate-500 dark:text-slate-400 ml-auto">
          共 {filteredUsers.length} 条结果
        </span>
      </motion.div>

      {/* Table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">用户</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">邮箱</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">角色</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">在线</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">系统账号</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">创建时间</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">最后登录</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">最后活动</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-16 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <User className="w-8 h-8 text-slate-300" />
                      <p>暂无用户数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedUsers.map((user, i) => (
                  <motion.tr
                    key={user.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.02 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400 font-mono">#{user.id}</span>
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {user.username}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                      {user.email || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {roleBadge(user.role)}
                        {isRoot() && user.role !== 'ROOT' && (
                          <button
                            onClick={() => openRoleModal(user)}
                            className="text-xs text-primary-500 hover:text-primary-600 hover:underline"
                          >
                            修改
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(user)}
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
                    <td className="px-4 py-3 text-xs">
                      {user.is_system_account ? (
                        <span className="text-purple-600 dark:text-purple-400 font-medium">系统</span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {formatDate(user.last_login_at)}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {formatDate(user.last_activity_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isRoot() && user.role !== 'ROOT' && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleToggleStatus(user)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                            title={user.is_active ? '禁用' : '启用'}
                          >
                            {user.is_active ? <ToggleRight className="w-4 h-4 text-green-500" /> : <ToggleLeft className="w-4 h-4" />}
                          </button>
                          <button
                            onClick={() => setDeleteModal({ user })}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="删除用户"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                      {isAdmin() && user.role !== 'ADMIN' && user.role !== 'ROOT' && (
                        <span className="text-xs text-slate-400">可管理</span>
                      )}
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-slate-500 dark:text-slate-400">
            第 {safeCurrentPage}/{totalPages} 页
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={safeCurrentPage <= 1}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, safeCurrentPage - 2)
              const page = start + i
              if (page > totalPages) return null
              return (
                <button
                  key={page}
                  onClick={() => setCurrentPage(page)}
                  className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
                    page === safeCurrentPage
                      ? 'bg-primary-500 text-white'
                      : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
                >
                  {page}
                </button>
              )
            })}
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={safeCurrentPage >= totalPages}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Role Change Modal */}
      {roleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl border border-slate-200 dark:border-slate-700"
          >
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
              修改用户角色
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
              用户: <strong>{roleModal.user.username}</strong>
            </p>
            <div className="space-y-2 mb-6">
              {ROLE_OPTIONS.map(r => (
                <label
                  key={r}
                  className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                    selectedNewRole === r
                      ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                      : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50'
                  }`}
                >
                  <input
                    type="radio"
                    name="role"
                    value={r}
                    checked={selectedNewRole === r}
                    onChange={() => setSelectedNewRole(r)}
                    className="text-primary-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{r}</span>
                  </div>
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setRoleModal(null)}
                className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleChangeRole}
                className="px-4 py-2 text-sm text-white bg-primary-500 rounded-xl hover:bg-primary-600 transition-colors"
              >
                确认修改
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl border border-slate-200 dark:border-slate-700"
          >
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">
              确认删除用户
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">
              该操作不可恢复，确认删除用户 <strong>{deleteModal.user.username}</strong>？
            </p>
            <p className="text-xs text-red-500 mb-6">
              此操作为软删除，用户数据将被标记为已删除但不会物理清除。
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteModal(null)}
                className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-sm text-white bg-red-500 rounded-xl hover:bg-red-600 transition-colors"
              >
                确认删除
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}