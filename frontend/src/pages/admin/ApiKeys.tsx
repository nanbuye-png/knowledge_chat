import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Key, Plus, Trash2, Copy, Check, Eye, EyeOff } from 'lucide-react'
import * as adminApi from '../../api/admin'

export default function ApiKeys() {
  const [keys, setKeys] = useState<adminApi.ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState<string | null>(null)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState<Record<number, boolean>>({})

  const fetchKeys = useCallback(async () => {
    try {
      const data = await adminApi.listApiKeys()
      setKeys(data)
    } catch { setMsg('加载失败') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchKeys() }, [fetchKeys])

  const handleCreate = async () => {
    try {
      const result = await adminApi.createApiKey(1)
      setNewKey(result.key)
      setMsg('API Key 已创建，请立即复制')
      await fetchKeys()
    } catch (err: any) { setMsg('创建失败: ' + (err.message || '')) }
  }

  const handleRevoke = async (id: number) => {
    if (!window.confirm('确定要撤销此 API Key 吗？')) return
    try {
      await adminApi.revokeApiKey(id)
      setMsg('API Key 已撤销')
      await fetchKeys()
    } catch (err: any) { setMsg('撤销失败: ' + (err.message || '')) }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setMsg('已复制到剪贴板')
    setTimeout(() => setMsg(null), 2000)
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">API Key 管理</h1>
          <p className="text-sm text-slate-500 mt-1">管理 API 访问密钥</p>
        </div>
        <button onClick={handleCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 text-sm">
          <Plus className="w-4 h-4" />创建 API Key
        </button>
      </div>

      {msg && (
        <div className={`mb-4 p-3 rounded-xl text-sm ${msg.includes('失败') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
          {msg}
          {newKey && (
            <button onClick={() => copyToClipboard(newKey)} className="ml-2 text-primary-500 underline">复制</button>
          )}
        </div>
      )}

      {newKey && (
        <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <p className="text-sm font-medium text-amber-800 mb-1">新创建的 API Key（仅显示一次）</p>
          <code className="text-sm bg-white px-3 py-2 rounded border border-amber-200 block break-all">{newKey}</code>
        </div>
      )}

      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">ID</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">API Key</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">用户</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">状态</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">调用次数</th>
              <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">创建时间</th>
              <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
            {keys.map((k) => (
              <tr key={k.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                <td className="px-4 py-3 text-xs font-mono text-slate-500">{k.id}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <code className="text-xs font-mono bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded">
                      {showKey[k.id] ? k.key : `${k.key.substring(0, 12)}...`}
                    </code>
                    <button onClick={() => setShowKey(prev => ({ ...prev, [k.id]: !prev[k.id] }))}
                      className="text-slate-400 hover:text-primary-500">
                      {showKey[k.id] ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                    </button>
                    <button onClick={() => copyToClipboard(k.key)}
                      className="text-slate-400 hover:text-primary-500">
                      <Copy className="w-3 h-3" />
                    </button>
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-600">{k.username}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${k.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {k.is_active ? '启用' : '禁用'}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500">{k.call_count}</td>
                <td className="px-4 py-3 text-xs text-slate-500">{new Date(k.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleRevoke(k.id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {keys.length === 0 && <div className="text-center py-12 text-slate-400">暂无 API Key</div>}
      </div>
    </div>
  )
}