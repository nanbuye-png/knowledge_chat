import { useState, useEffect, useCallback } from 'react'
import * as adminApi from '../../api/admin'

export default function AuditLogs() {
  const [logs, setLogs] = useState<adminApi.AuditLogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const pageSize = 20

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await adminApi.listAuditLogs({ page, page_size: pageSize })
      setLogs(resp.items || [])
      setTotal(resp.total || 0)
    } catch {} finally { setLoading(false) }
  }, [page])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8" /></div>

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">审计日志</h1>
      <p className="text-sm text-slate-500 mb-6">系统操作记录（共 {total} 条）</p>
      <div className="bg-white rounded-2xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-slate-50">
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作者</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">目标</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">IP</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">状态</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">时间</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {logs.map((log) => (
              <tr key={log.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-700">#{log.operator_id}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">
                    {log.action}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs">{log.target_type}:{log.target_id || '-'}</td>
                <td className="px-4 py-3 text-xs font-mono text-slate-400">{log.ip_address || '-'}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${log.status === 'SUCCESS' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {log.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">{log.created_at ? new Date(log.created_at).toLocaleString() : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {logs.length === 0 && <div className="text-center py-12 text-slate-400">暂无审计日志</div>}
        {total > pageSize && (
          <div className="flex justify-center gap-2 p-4 border-t">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="px-3 py-1 text-sm rounded border disabled:opacity-50">上一页</button>
            <span className="px-3 py-1 text-sm text-slate-500">{page} / {Math.ceil(total / pageSize)}</span>
            <button disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage(p => p + 1)} className="px-3 py-1 text-sm rounded border disabled:opacity-50">下一页</button>
          </div>
        )}
      </div>
    </div>
  )
}