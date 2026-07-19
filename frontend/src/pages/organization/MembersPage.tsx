import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Users, Shield, ShieldAlert, User, UserMinus, Search, Building2 } from 'lucide-react'
import * as orgApi from '../../api/organizations'
import type { Organization, OrganizationMember } from '../../api/organizations'
import { usePermission } from '../../hooks/usePermission'

const MEMBER_ROLES = ['OWNER', 'ADMIN', 'MEMBER'] as const

function roleBadge(role: string) {
  if (role === 'OWNER') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"><ShieldAlert className="w-3 h-3" />OWNER</span>
  }
  if (role === 'ADMIN') {
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"><Shield className="w-3 h-3" />ADMIN</span>
  }
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"><User className="w-3 h-3" />MEMBER</span>
}

export default function MembersPage() {
  const { isRoot, isAdmin } = usePermission()
  const canManage = isRoot() || isAdmin()

  const [org, setOrg] = useState<Organization | null>(null)
  const [members, setMembers] = useState<OrganizationMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<OrganizationMember | null>(null)

  const showMessage = (msg: string) => {
    setActionMsg(msg)
    setTimeout(() => setActionMsg(null), 3000)
  }

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const orgRes = await orgApi.listOrganizations(0, 1)
      if (orgRes.items.length === 0) {
        setLoading(false)
        return
      }
      const currentOrg = orgRes.items[0]
      setOrg(currentOrg)
      const memberList = await orgApi.listMembers(currentOrg.id)
      setMembers(memberList)
    } catch (err: any) {
      setError(err.message || '成员加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleRemoveMember = async () => {
    if (!confirmRemove || !org) return
    try {
      await orgApi.removeMember(org.id, confirmRemove.user_id)
      showMessage(`已移除成员 #${confirmRemove.user_id}`)
      setConfirmRemove(null)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const handleRoleChange = async (member: OrganizationMember, newRole: string) => {
    if (!org) return
    try {
      await orgApi.updateMemberRole(org.id, member.user_id, newRole)
      showMessage(`成员角色已更新`)
      await fetchData()
    } catch (err: any) {
      showMessage(`操作失败: ${err.message}`)
    }
  }

  const filtered = searchKeyword.trim()
    ? members.filter(m => String(m.user_id).includes(searchKeyword.trim()))
    : members

  // ---------- Render ----------

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-500">
        <p className="mb-4">{error}</p>
        <button onClick={fetchData} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
      </div>
    )
  }

  if (!org) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-400">
        <Building2 className="w-12 h-12 mb-3" />
        <p>暂无组织，请联系 ROOT 管理员创建</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Users className="w-6 h-6 text-blue-500" />
          组织成员
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {org.name} · 共 {members.length} 名成员
        </p>
      </motion.div>

      {actionMsg && (
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 text-sm text-primary-700 dark:text-primary-300">
          {actionMsg}
        </motion.div>
      )}

      {/* Search */}
      <div className="relative mb-6 max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text" value={searchKeyword} onChange={e => setSearchKeyword(e.target.value)}
          placeholder="搜索用户 ID..."
          className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
        />
      </div>

      {/* Members table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">用户 ID</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">角色</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">加入时间</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {filtered.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-16 text-slate-400">暂无成员</td></tr>
              ) : (
                filtered.map((m, i) => (
                  <motion.tr key={m.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">#{m.user_id}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {roleBadge(m.role)}
                        {canManage && m.role !== 'OWNER' && (
                          <select
                            value={m.role}
                            onChange={e => handleRoleChange(m, e.target.value)}
                            className="text-xs bg-transparent border border-slate-200 dark:border-slate-600 rounded px-1.5 py-0.5 text-slate-400 cursor-pointer hover:border-primary-300"
                          >
                            {MEMBER_ROLES.map(r => <option key={r} value={r} disabled={r === 'OWNER'}>{r}</option>)}
                          </select>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {m.is_active ? <span className="text-green-600 dark:text-green-400">正常</span> : <span className="text-red-600 dark:text-red-400">已禁用</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {m.joined_at ? new Date(m.joined_at).toLocaleDateString('zh-CN') : '-'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canManage && m.role !== 'OWNER' && (
                        <button onClick={() => setConfirmRemove(m)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors" title="移除成员">
                          <UserMinus className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Remove confirm modal */}
      {confirmRemove && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl border">
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">确认移除成员</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
              确定将成员 <strong>#{confirmRemove.user_id}</strong> 从组织中移除？
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmRemove(null)}
                className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-600">
                取消
              </button>
              <button onClick={handleRemoveMember}
                className="px-4 py-2 text-sm text-white bg-red-500 rounded-xl hover:bg-red-600">
                确认移除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

