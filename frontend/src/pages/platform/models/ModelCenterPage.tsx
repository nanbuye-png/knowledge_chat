import { useEffect, useState } from 'react'
import { Cpu, Plus, ToggleLeft, ToggleRight, Edit3, Trash2 } from 'lucide-react'
import LoadingState from '../../../components/common/LoadingState'
import EmptyState from '../../../components/common/EmptyState'
import { listModels, updateModel, createModel, deleteModel, type LLMModel, type LLMModelCreate } from '../../../api/models'

export default function ModelCenterPage() {
  const [models, setModels] = useState<LLMModel[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<LLMModelCreate>({ name: '', provider: 'deepseek', model_name: '' })
  const [editId, setEditId] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    listModels().then(setModels).catch(() => setModels([])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const toggleEnabled = async (m: LLMModel) => {
    await updateModel(m.id, { enabled: !m.enabled })
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此模型？')) return
    await deleteModel(id)
    load()
  }

  const handleSubmit = async () => {
    if (editId) {
      await updateModel(editId, form)
    } else {
      await createModel(form)
    }
    setShowForm(false)
    setEditId(null)
    setForm({ name: '', provider: 'deepseek', model_name: '' })
    load()
  }

  const startEdit = (m: LLMModel) => {
    setForm({ name: m.name, provider: m.provider, model_name: m.model_name })
    setEditId(m.id)
    setShowForm(true)
  }

  if (loading) return <LoadingState text="加载模型列表..." />

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-3">
          <Cpu className="w-6 h-6 text-purple-500" />
          Model Center
        </h1>
        <button onClick={() => { setShowForm(true); setEditId(null); setForm({ name: '', provider: 'deepseek', model_name: '' }) }}
          className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600">
          <Plus className="w-3.5 h-3.5" /> Add Model
        </button>
      </div>

      {showForm && (
        <div className="mb-6 p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
          <div className="grid grid-cols-3 gap-3 mb-3">
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
            <input placeholder="Provider (e.g. deepseek)" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}
              className="px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
            <input placeholder="Model Name (e.g. deepseek-chat)" value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })}
              className="px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
          </div>
          <div className="flex gap-2">
            <button onClick={handleSubmit} className="px-4 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600">
              {editId ? 'Update' : 'Create'}
            </button>
            <button onClick={() => { setShowForm(false); setEditId(null) }} className="px-4 py-1.5 text-sm rounded-xl border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {models.length === 0 ? (
        <EmptyState icon={Cpu} title="No models available" description="点击 Add Model 添加模型" />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-slate-500">Name</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500">Provider</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500">Model Name</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500">Status</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500">Created</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {models.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-white">{m.name}</td>
                  <td className="px-4 py-3 text-slate-500">{m.provider}</td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{m.model_name}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleEnabled(m)}
                      className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${m.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                      {m.enabled ? <ToggleRight className="w-3 h-3" /> : <ToggleLeft className="w-3 h-3" />}
                      {m.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{m.created_at ? new Date(m.created_at).toLocaleDateString() : '--'}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => startEdit(m)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Edit3 className="w-3.5 h-3.5" /></button>
                    <button onClick={() => handleDelete(m.id)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500 ml-1"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}