import { useCallback, useEffect, useState } from 'react'
import { Monitor, Smartphone, Clock, Trash2, CheckCircle, AlertTriangle } from 'lucide-react'
import EmptyState from '../../components/common/EmptyState'
import LoadingState from '../../components/common/LoadingState'
import apiClient from '../../api/client'

/**
 * 接口契约（后端 backend/app/api/auth_sessions.py）
 * ---------------------------------------------------------------------------
 * apiClient 的 baseURL 已经是 '/api'（见 api/client.ts），所以这里的路径必须
 * 写成 '/auth/sessions'，最终请求的是 /api/auth/sessions。
 *
 * 历史缺陷（审计 §5.15）：
 *   1. 列表字段全错位 —— 页面读 device / ip / last_active / is_current，
 *      后端返回的却是 device_info / ip_address / last_used_at / is_active
 *      （is_current 当时**根本没实现**）→ 卡片永远显示 "Unknown Device"、
 *      "IP: --"、时间 "--"，"当前设备"徽标永不出现；
 *   2. 请求写在 useState(() => {...}) 里 —— 在 render 期间发请求（StrictMode
 *      下会重复请求，且 loading 状态与 React 生命周期脱钩）；
 *   3. 页面只读：看到陌生设备**无法退出**（后端当时也没有用户端注销接口）。
 * 现在字段逐一对齐、加载放进 useEffect，并调用
 * DELETE /api/auth/sessions/{id} 支持"退出该设备"。
 */
interface SessionItem {
  id: number
  device_info: string | null
  ip_address: string | null
  created_at: string | null
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
  is_active: boolean
  is_current: boolean
}

/** 响应拦截器已把错误统一成 `new Error(message)`（见 api/client.ts:100）。 */
function errorMessageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

function formatTime(value: string | null): string {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleString()
}

/** device_info 是登录时记录的 User-Agent，粗判移动端只为了换个图标。 */
function isMobileDevice(deviceInfo: string | null): boolean {
  return /Mobile|Android|iPhone|iPad/i.test(deviceInfo ?? '')
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [revoking, setRevoking] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadSessions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/auth/sessions')
      setSessions(Array.isArray(res.data) ? res.data : [])
      setError('')
    } catch (err) {
      setSessions([])
      setError(errorMessageOf(err, '加载会话列表失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadSessions() }, [loadSessions])

  const handleRevoke = async (session: SessionItem) => {
    setRevoking(session.id)
    setError('')
    setMessage('')
    try {
      const res = await apiClient.delete(`/auth/sessions/${session.id}`)
      setMessage(res.data?.message ?? '已退出该设备')
      await loadSessions()
    } catch (err) {
      setError(errorMessageOf(err, '注销会话失败'))
    } finally {
      setRevoking(null)
    }
  }

  if (loading) return <LoadingState text="加载会话列表..." />

  const list = sessions ?? []
  const activeCount = list.filter((s) => s.is_active).length

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-xl font-bold text-slate-800 dark:text-white mb-2 flex items-center gap-2">
        <Monitor className="w-5 h-5 text-primary-500" />
        Sessions
      </h2>
      <p className="text-xs text-slate-400 mb-4">
        共 {list.length} 条登录记录 · {activeCount} 台设备在线
      </p>

      {message && (
        <div className="mb-4 flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2">
          <CheckCircle className="w-3 h-3 shrink-0" />{message}
        </div>
      )}
      {error && (
        <div className="mb-4 flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
          <AlertTriangle className="w-3 h-3 shrink-0" />{error}
        </div>
      )}

      {list.length === 0 ? (
        <EmptyState icon={Smartphone} title="暂无登录设备记录" />
      ) : (
        <div className="space-y-3">
          {list.map((s) => (
            <div key={s.id} className="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-4">
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="flex items-center gap-2 min-w-0 text-sm font-medium text-slate-800 dark:text-white">
                  {isMobileDevice(s.device_info)
                    ? <Smartphone className="w-4 h-4 text-slate-400 shrink-0" />
                    : <Monitor className="w-4 h-4 text-slate-400 shrink-0" />}
                  <span className="truncate" title={s.device_info ?? ''}>{s.device_info || '未知设备'}</span>
                </span>
                <span className="flex items-center gap-1 shrink-0">
                  {s.is_current && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Current</span>
                  )}
                  {!s.is_active && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                      {s.revoked_at ? '已退出' : '已过期'}
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 text-xs text-slate-400">
                <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span>IP: {s.ip_address || '--'}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />最后活跃 {formatTime(s.last_used_at)}
                  </span>
                  <span>创建 {formatTime(s.created_at)}</span>
                </span>
                {s.is_active && !s.is_current && (
                  <button
                    type="button"
                    onClick={() => void handleRevoke(s)}
                    disabled={revoking === s.id}
                    className="flex items-center gap-1 shrink-0 px-2 py-1 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                  >
                    <Trash2 className="w-3 h-3" />{revoking === s.id ? '注销中...' : '退出该设备'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
