import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { FileText, Plus, Edit3, Trash2, Eye, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import * as promptApi from '../../api/prompts'
import type { PromptTemplate, PromptCreate } from '../../api/prompts'

export default function PromptManagementPage() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState<PromptCreate>({ name: '', prompt_type: 'system', content: '' })

  const showMessage = (msg: string) => { setActionMsg(msg); setTimeout(() => setActionMsg(null), 3000) }

  const fetchPrompts = useCallback(async () => {
    try {
      setError(null)
      const list = await promptApi.listPrompts()
      setPrompts(list)
    } catch (err: any) { setError(err.message || 'Prompt 列表加载失败') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchPrompts() }, [fetchPrompts])

  const handleToggleActive = async (p: PromptTemplate) => {
    try {
      await promptApi.updatePrompt(p.id, { is_active: !p.is_active })
      showMessage(`Prompt "${p.name}" 已${!p.is_active ? '激活' : '停用'}`)
      await fetchPrompts()
    } catch (err: any) { showMessage(`操作失败: ${err.message}`) }
  }

  const handleDelete = async (p: PromptTemplate) => {
    if (!window.confirm(`确定删除 Prompt "${p.name}"？`)) return
    try {
      await promptApi.deletePrompt(p.id)
      showMessage(`Prompt "${p.name}" 已删除`)
      await fetchPrompts()
    } catch (err: any) { showMessage(`操作失败: ${err.message}`) }
  }

  const handleCreate = async () => {
    if (!createForm.name || !createForm.content) return
    try {
      await promptApi.createPrompt(createForm)
      showMessage('Prompt 创建成功')
      setShowCreate(false)
      setCreateForm({ name: '', prompt_type: 'system', content: '' })
      await fetchPrompts()
    } catch (err: any) { showMessage(`创建失败: ${err.message}`) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-red-500">
      <p className="mb-4">{error}</p>
      <button onClick={fetchPrompts} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
    </div>
  )

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <FileText className="w-6 h-6 text-emerald-500" />Prompt Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">提示词模板管理</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600 transition-colors">
          <Plus className="w-4 h-4" />新建 Prompt
        </button>
      </motion.div>

      {actionMsg && <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
        className="mb-4 p-3 rounded-xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 text-sm text-primary-700">{actionMsg}</motion.div>}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 w-full max-w-lg mx-4 shadow-2xl border">
            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">新建 Prompt</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1">名称</label>
                <input value={createForm.name} onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">类型</label>
                <select value={createForm.prompt_type} onChange={e => setCreateForm({ ...createForm, prompt_type: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                  <option value="system">System</option>
                  <option value="user">User</option>
                  <option value="assistant">Assistant</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">内容</label>
                <textarea value={createForm.content} onChange={e => setCreateForm({ ...createForm, content: e.target.value })} rows={5}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono" />
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
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">名称</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">类型</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">版本</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">激活</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">启用</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">更新时间</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {prompts.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-16 text-slate-400">暂无 Prompt 数据</td></tr>
              ) : (
                prompts.map((p, i) => (
                  <motion.tr key={p.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">{p.name}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{p.prompt_type}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-600">v{p.version}</td>
                    <td className="px-4 py-3">
                      {p.is_active
                        ? <span className="inline-flex items-center gap-1 text-xs text-green-600"><CheckCircle className="w-3 h-3" />激活</span>
                        : <span className="inline-flex items-center gap-1 text-xs text-slate-400"><XCircle className="w-3 h-3" />停用</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {p.enabled
                        ? <span className="text-green-600">是</span>
                        : <span className="text-slate-400">否</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{p.updated_at ? new Date(p.updated_at).toLocaleDateString('zh-CN') : '-'}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => handleToggleActive(p)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                          title={p.is_active ? '停用' : '激活'}>
                          <Eye className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(p)}
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