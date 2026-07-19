import { Monitor, Clock, Smartphone } from 'lucide-react'
import { useState } from 'react'
import EmptyState from '../../components/common/EmptyState'
import LoadingState from '../../components/common/LoadingState'
import apiClient from '../../api/client'

interface Session {
  id: number
  device: string
  ip: string
  created_at: string
  last_active: string
  is_current: boolean
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[] | null>(null)
  const [loading, setLoading] = useState(true)

  // Try loading sessions
  useState(() => {
    apiClient.get('/auth/sessions')
      .then((res) => setSessions(res.data || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false))
  })

  if (loading) return <LoadingState text="加载会话列表..." />

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-2">
        <Monitor className="w-5 h-5 text-primary-500" />
        Sessions
      </h2>

      {!sessions || sessions.length === 0 ? (
        <EmptyState icon={Smartphone} title="暂无登录设备记录" />
      ) : (
        <div className="space-y-3">
          {sessions.map((s) => (
            <div key={s.id} className="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-800 dark:text-white">{s.device || 'Unknown Device'}</span>
                {s.is_current && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Current</span>
                )}
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-400">
                <span>IP: {s.ip || '--'}</span>
                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{s.last_active ? new Date(s.last_active).toLocaleDateString() : '--'}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}