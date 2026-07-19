import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Cpu, Power, PowerOff, Star, Plus, Trash2, Edit3, RefreshCw } from 'lucide-react'
import * as modelApi from '../../api/models'
import type { LLMModel, LLMModelCreate } from '../../api/models'

export default function ModelRegistryPage() {
  const [models, setModels] = useState<LLMModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState<LLMModelCreate>({ name: '', provider: '', model_name: '' })

  const showMessage = (msg: string) => { setActionMsg(msg); setTimeout(() => setActionMsg(null), 3000) }

  const fetchModels = useCallback(async () => {
    try {
      setError(null)
      const list = await modelApi.listModels()
      setModels(list)
    } catch (err: any) {
      setError(err.message || '模型列表加载失败')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchModels() }, [fetchModels])

  const handleToggle = async (m: LLMModel) => {
    try {
      await modelApi.updateModel(m.id, { enabled: !m.enabled })
      showMessage(`模型 ${m.name} 已${!m.enabled ? '启用' : '禁用'}`)
      await fetchModels()
    } catch (err: any) { showMessage(`操作失败: ${err.message}`) }
  }

  const handleDelete = async (m: LLMModel) => {
    if (!window.confirm(`确定删除模型 "${m.name}"？`)) return
    try {
      await modelApi.deleteModel(m.id)
      showMessage(`模型 ${m.name} 已删除`)
      await fetchModels()
    } catch (err: any) { showMessage(`操作失败: ${err.message}`) }
  }

  const handleCreate = async () => {
    if (!createForm.name || !createForm.provider || !createForm.model_name) return
    try {
      await modelApi.createModel(createForm)
      showMessage('模型创建成功')
      setShowCreate(false)
      setCreateForm({ name: '', provider: '', model_name: '' })
      await fetchModels()
    } catch (err: any) { showMessage(`创建失败: ${err.message}`) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchModels} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Cpu className="w-6 h-6 text-cyan-500" />Model Registry
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI 模型注册表管理</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600 transition-colors">
          <Plus className="w-4 h-4" />新建模型
        </button>
      </motion.div>

      {actionMsg && <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
        className="mb-4 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 text-sm text-primary-700">{actionMsg}</motion.div>}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl border">
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">新建模型</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1">名称</label>
                <input value={createForm.name} onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Provider</label>
                <input value={createForm.provider} onChange={e => setCreateForm({ ...createForm, provider: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">模型名</label>
                <input value={createForm.model_name} onChange={e => setCreateForm({ ...createForm, model_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm text-slate-600 bg-slate-100 dark:bg-slate-700 rounded-xl hover:bg-slate-200">取消</button>
              <button onClick={handleCreate}
                className="px-4 py-2 text-sm text-white bg-primary-500 rounded-xl hover:bg-primary-600">创建</button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">Provider</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">Model Name</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">显示名称</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">创建时间</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {models.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-16 text-slate-400">暂无模型数据</td></tr>
              ) : (
                models.map((m, i) => (
                  <motion.tr key={m.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-300">{m.provider}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{m.model_name}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{m.name}</td>
                    <td className="px-4 py-3">
                      {m.enabled
                        ? <span className="inline-flex items-center gap-1 text-xs text-green-600"><span className="w-1.5 h-1.5 rounded-full bg-green-500" />启用</span>
                        : <span className="inline-flex items-center gap-1 text-xs text-slate-400"><span className="w-1.5 h-1.5 rounded-full bg-slate-300" />禁用</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{m.created_at ? new Date(m.created_at).toLocaleDateString('zh-CN') : '-'}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => handleToggle(m)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                          title={m.enabled ? '禁用' : '启用'}>
                          {m.enabled ? <Power className="w-4 h-4 text-green-500" /> : <PowerOff className="w-4 h-4" />}
                        </button>
                        <button onClick={() => handleDelete(m)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors" title="删除">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}