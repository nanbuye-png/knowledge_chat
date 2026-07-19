import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { FileText, Search, ChevronLeft, ChevronRight, Filter, RefreshCw } from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { AuditLogItem } from '../../api/admin'

const PAGE_SIZE = 25

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [searchAction, setSearchAction] = useState('')

  const fetchLogs = useCallback(async () => {
    try {
      setError(null)
      setLoading(true)
      const resp = await adminApi.listAuditLogs({ page, page_size: PAGE_SIZE })
      setLogs(resp.items || [])
      setTotal(resp.total || 0)
    } catch (err: any) { setError(err.message || '审计日志加载失败') }
    finally { setLoading(false) }
  }, [page])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  const filtered = searchAction.trim()
    ? logs.filter(l => l.action.toLowerCase().includes(searchAction.toLowerCase()))
    : logs

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (loading && logs.length === 0) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchLogs} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <FileText className="w-6 h-6 text-blue-500" />Audit Logs
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">系统操作审计日志（共 {total} 条）</p>
        </div>
        <button onClick={fetchLogs} className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors">
          <RefreshCw className="w-4 h-4" />刷新
        </button>
      </motion.div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="text" value={searchAction} onChange={e => setSearchAction(e.target.value)}
            placeholder="筛选操作类型..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/30" />
        </div>
        <span className="text-sm text-slate-400">当前页 {filtered.length} 条</span>
      </div>

      {/* Table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">操作者</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">操作</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">目标</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">IP</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">User Agent</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 dark:text-slate-400 text-xs uppercase">时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {filtered.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-16 text-slate-400">暂无审计日志</td></tr>
              ) : (
                filtered.map((log, i) => (
                  <motion.tr key={log.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.01 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-300">#{log.operator_id}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{log.target_type}:{log.target_id || '-'}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-400">{log.ip_address || '-'}</td>
                    <td className="px-4 py-3 text-xs text-slate-400 max-w-[200px] truncate">{log.user_agent || '-'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        log.status === 'SUCCESS' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                        : log.status === 'FAILED' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                        : 'bg-slate-100 text-slate-600'
                      }`}>{log.status}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : '-'}
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
          <span className="text-sm text-slate-500">第 {page}/{totalPages} 页</span>
          <div className="flex items-center gap-2">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-slate-600 dark:text-slate-300">第 {page} 页</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}