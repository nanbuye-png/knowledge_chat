import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, FileText, RefreshCw, Search } from 'lucide-react'
import * as adminApi from '../../api/admin'
import type { AuditLogItem } from '../../api/admin'

export default function ErrorTrackingPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetchErrors = useCallback(async () => {
    try {
      const resp = await adminApi.listAuditLogs({ page: 1, page_size: 50 })
      setLogs((resp.items || []).filter(l => l.status === 'FAILED'))
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchErrors() }, [fetchErrors])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3"><AlertTriangle className="w-6 h-6 text-red-500" />Error Tracking</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">系统错误追踪（基于审计日志）</p>
        </div>
        <button onClick={fetchErrors} className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg"><RefreshCw className="w-4 h-4" />刷新</button>
      </motion.div>

      {logs.length === 0 ? (
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-16 text-center text-slate-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>暂无错误记录</p>
          <p className="text-xs mt-1">当前错误数据仅来自审计日志中的 FAILED 记录</p>
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">时间</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">级别</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作者</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">目标</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                {logs.map((log, i) => (
                  <motion.tr key={log.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.01 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="px-4 py-3"><span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">FAILED</span></td>
                    <td className="px-4 py-3 font-medium text-slate-700">#{log.operator_id}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-600">{log.action}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{log.target_type}:{log.target_id || '-'}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-400">{log.ip_address || '-'}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}