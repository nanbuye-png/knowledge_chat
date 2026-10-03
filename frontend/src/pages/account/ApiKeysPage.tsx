import { useCallback, useEffect, useState } from 'react'
import { Key, Plus, Trash2, Copy, CheckCircle, AlertTriangle } from 'lucide-react'
import EmptyState from '../../components/common/EmptyState'
import LoadingState from '../../components/common/LoadingState'
import apiClient from '../../api/client'

/**
 * 接口契约（后端 backend/app/api/api_keys.py）
 * ---------------------------------------------------------------------------
 * apiClient 的 baseURL 已经是 '/api'（见 api/client.ts），所以这里的路径必须
 * 写成 '/api-keys'，最终请求的是 /api/api-keys。
 *
 * 历史缺陷（审计 Phase A）：本页此前调用 '/admin/api-keys' —— 那是并不存在的
 * 管理端路径（后端只有用户端 '/api/api-keys'）；创建时发送 `{ user_id: 0 }`，
 * 真实 body 是 `{ name }`；响应字段被当成 `key`，而列表里其实只有 `key_prefix`
 * （明文只在创建响应 `api_key` 里返回一次）。结果就是"永远空列表 + 创建必 404 +
 * 复制到 undefined"。现在逐字段对齐，并由
 * backend/tests/test_api_key_contract.py 断言两侧一致。
 */
interface ApiKeyItem {
  id: number
  name: string
  key_prefix: string
  is_active: boolean
  last_used_at: string | null
  expires_at: string | null
  created_at: string | null
}

interface CreatedApiKey {
  id: number
  name: string
  api_key: string
  created_at: string | null
}

/** 响应拦截器已把错误统一成 `new Error(message)`（见 api/client.ts:100）。 */
function errorMessageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null)
  const [copied, setCopied] = useState('')
  const [error, setError] = useState('')

  const loadKeys = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/api-keys')
      setKeys(Array.isArray(res.data) ? res.data : [])
      setError('')
    } catch (err) {
      setKeys([])
      setError(errorMessageOf(err, '加载 API Key 失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadKeys()
  }, [loadKeys])

  const handleCreate = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('请先填写 Key 名称')
      return
    }
    setCreating(true)
    try {
      const res = await apiClient.post('/api-keys', { name: trimmed })
      setCreatedKey(res.data as CreatedApiKey)
      setName('')
      setError('')
      await loadKeys()
    } catch (err) {
      setError(errorMessageOf(err, '创建 API Key 失败'))
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (id: number) => {
    try {
      await apiClient.patch(`/api-keys/${id}/revoke`)
      setError('')
      await loadKeys()
    } catch (err) {
      setError(errorMessageOf(err, '撤销 API Key 失败'))
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await apiClient.delete(`/api-keys/${id}`)
      setError('')
      await loadKeys()
    } catch (err) {
      setError(errorMessageOf(err, '删除 API Key 失败'))
    }
  }

  const handleCopy = (token: string, text: string) => {
    void navigator.clipboard.writeText(text)
    setCopied(token)
    setTimeout(() => setCopied(''), 2000)
  }

  if (loading) return <LoadingState text="加载 API Keys..." />

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center gap-2">
          <Key className="w-5 h-5 text-primary-500" />
          API Keys
        </h2>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key 名称（如：CI 机器人）"
          className="flex-1 px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500"
        />
        <button
          onClick={handleCreate}
          disabled={creating}
          className="flex items-center gap-1 px-3 py-2 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          {creating ? 'Creating...' : 'Create Key'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
        </div>
      )}

      {createdKey && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300 mb-1">
            ✅ 已创建「{createdKey.name}」—— 明文只返回这一次，请立即保存
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs bg-white dark:bg-slate-800 px-2 py-1 rounded break-all">
              {createdKey.api_key}
            </code>
            <button
              onClick={() => handleCopy('created', createdKey.api_key)}
              className="p-1.5 rounded-lg hover:bg-white/60 dark:hover:bg-slate-700 text-slate-500"
              title="Copy"
            >
              {copied === 'created' ? (
                <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      )}

      {!keys || keys.length === 0 ? (
        <EmptyState icon={Key} title="暂无 API Key" description="填写名称后点击 Create Key 创建" />
      ) : (
        <div className="space-y-2">
          {keys.map((k) => (
            <div key={k.id} className="flex items-center justify-between p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-slate-800 dark:text-white">{k.name}</span>
                  <code className="text-xs text-slate-500">{k.key_prefix}…</code>
                  {k.is_active ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Active</span>
                  ) : (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-700">Revoked</span>
                  )}
                </div>
                <p className="text-xs text-slate-400">
                  Created: {k.created_at ? new Date(k.created_at).toLocaleDateString() : '--'}
                  {k.last_used_at ? ` · Last used: ${new Date(k.last_used_at).toLocaleDateString()}` : ''}
                  {k.expires_at ? ` · Expires: ${new Date(k.expires_at).toLocaleDateString()}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-1">
                {k.is_active && (
                  <button
                    onClick={() => handleRevoke(k.id)}
                    className="px-2 py-1 text-xs rounded-lg text-slate-500 hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-900/20"
                    title="撤销（保留记录，is_active=false）"
                  >
                    撤销
                  </button>
                )}
                <button
                  onClick={() => handleDelete(k.id)}
                  className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500"
                  title="删除（物理删除）"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}