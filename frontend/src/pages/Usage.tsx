import { useState, useEffect } from 'react'
import { BarChart3, Zap, Clock, Hash } from 'lucide-react'
import * as usageApi from '../api/usage'
import type { UsageStats, UsageRecord } from '../api/usage'

export default function Usage() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [records, setRecords] = useState<UsageRecord[]>([])

  useEffect(() => {
    usageApi.getUsageStats().then(setStats).catch(console.error)
    usageApi.getRecentUsage(20).then(setRecords).catch(console.error)
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-6">用量统计</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm">
          <div className="flex items-center gap-2 text-slate-500 mb-2"><Hash className="w-4 h-4" />总调用次数</div>
          <div className="text-2xl font-bold text-primary-500">{stats?.total_calls ?? '-'}</div>
        </div>
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm">
          <div className="flex items-center gap-2 text-slate-500 mb-2"><Zap className="w-4 h-4" />总 Token 量</div>
          <div className="text-2xl font-bold text-amber-500">{stats?.total_tokens?.toLocaleString() ?? '-'}</div>
        </div>
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm">
          <div className="flex items-center gap-2 text-slate-500 mb-2"><Clock className="w-4 h-4" />平均延迟 (ms)</div>
          <div className="text-2xl font-bold text-green-500">{stats?.avg_latency_ms ?? '-'}</div>
        </div>
      </div>

      <h2 className="text-lg font-semibold text-slate-800 dark:text-white mb-3">最近调用记录</h2>
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            <tr>
              <th className="text-left p-3">Provider</th>
              <th className="text-left p-3">Model</th>
              <th className="text-right p-3">Tokens</th>
              <th className="text-right p-3">Latency (ms)</th>
              <th className="text-right p-3">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {records.map(r => (
              <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-750">
                <td className="p-3 font-medium">{r.provider}</td>
                <td className="p-3 text-slate-500">{r.model}</td>
                <td className="p-3 text-right">{r.total_tokens}</td>
                <td className="p-3 text-right">{r.latency_ms.toFixed(0)}</td>
                <td className="p-3 text-right text-slate-400 text-xs">{new Date(r.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-slate-400">暂无记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}