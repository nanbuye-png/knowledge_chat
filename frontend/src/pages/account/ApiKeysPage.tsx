import { useState, useEffect } from 'react'
import { Key, Plus, Trash2, Copy, CheckCircle } from 'lucide-react'
import EmptyState from '../../components/common/EmptyState'
import LoadingState from '../../components/common/LoadingState'
import apiClient from '../../api/client'

interface ApiKey {
  id: number
  key: string
  name: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState('')
  const [copiedId, setCopiedId] = useState<number | null>(null)

  const loadKeys = () => {
    setLoading(true)
    apiClient.get('/admin/api-keys')
      .then((res) => setKeys(res.data || []))
      .catch(() => setKeys([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadKeys() }, [])

  const handleCreate = async () => {
    try {
      const res = await apiClient.post('/admin/api-keys', { user_id: 0 })
      setNewKey(res.data.key)
      loadKeys()
    } catch { /* ignore */ }
  }

  const handleRevoke = async (id: number) => {
    try {
      await apiClient.delete(`/admin/api-keys/${id}`)
      loadKeys()
    } catch { /* ignore */ }
  }

  const handleCopy = (id: number, key: string) => {
    navigator.clipboard.writeText(key)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  if (loading) return <LoadingState text="加载 API Keys..." />

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center gap-2">
          <Key className="w-5 h-5 text-primary-500" />
          API Keys
        </h2>
        <button
          onClick={handleCreate}
          className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Create Key
        </button>
      </div>

      {newKey && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300 mb-1">✅ Key created - copy it now</p>
          <code className="text-xs bg-white dark:bg-slate-800 px-2 py-1 rounded break-all">{newKey}</code>
        </div>
      )}

      {!keys || keys.length === 0 ? (
        <EmptyState icon={Key} title="暂无 API Key" description="点击 Create Key 创建" />
      ) : (
        <div className="space-y-2">
          {keys.map((k) => (
            <div key={k.id} className="flex items-center justify-between p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-slate-800 dark:text-white">{k.key?.slice(0, 20)}...</span>
                  {k.is_active ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Active</span>
                  ) : (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-700">Revoked</span>
                  )}
                </div>
                <p className="text-xs text-slate-400">
                  Created: {k.created_at ? new Date(k.created_at).toLocaleDateString() : '--'}
                  {k.last_used_at ? ` · Last used: ${new Date(k.last_used_at).toLocaleDateString()}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => handleCopy(k.id, k.key)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400" title="Copy">
                  {copiedId === k.id ? <CheckCircle className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
                {k.is_active && (
                  <button onClick={() => handleRevoke(k.id)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500" title="Revoke">
                    <Trash2 className="w-3.5 h-3.5" />
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