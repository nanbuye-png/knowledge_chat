import { useState, useEffect } from 'react'
import { Plus, Trash2, Edit3, Check, X } from 'lucide-react'
import * as promptsApi from '../api/prompts'
import type { PromptTemplate } from '../api/prompts'

export default function Prompts() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState({ name: '', prompt_type: 'system', content: '' })

  const load = () => promptsApi.listPrompts().then(setTemplates).catch(console.error)
  useEffect(() => { load() }, [])

  const resetForm = () => { setForm({ name: '', prompt_type: 'system', content: '' }); setShowCreate(false); setEditId(null) }

  const handleCreate = async () => {
    await promptsApi.createPrompt(form)
    resetForm(); load()
  }

  const handleUpdate = async (id: number) => {
    await promptsApi.updatePrompt(id, form)
    resetForm(); load()
  }

  const handleDelete = async (id: number) => {
    await promptsApi.deletePrompt(id)
    load()
  }

  const startEdit = (t: PromptTemplate) => {
    setEditId(t.id)
    setForm({ name: t.name, prompt_type: t.prompt_type, content: t.content })
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white">Prompt 管理</h1>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-1 px-4 py-2 bg-primary-500 text-white rounded-xl text-sm font-medium hover:bg-primary-600">
          <Plus className="w-4 h-4" />新建
        </button>
      </div>

      {(showCreate || editId !== null) && (
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm mb-6 space-y-3">
          <input className="w-full p-2 border rounded-lg dark:bg-slate-700 dark:border-slate-600" placeholder="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
          <select className="w-full p-2 border rounded-lg dark:bg-slate-700 dark:border-slate-600" value={form.prompt_type} onChange={e => setForm({ ...form, prompt_type: e.target.value })}>
            <option value="system">system</option><option value="rag">rag</option><option value="chat">chat</option>
          </select>
          <textarea className="w-full p-2 border rounded-lg dark:bg-slate-700 dark:border-slate-600 h-32" placeholder="Content" value={form.content} onChange={e => setForm({ ...form, content: e.target.value })} />
          <div className="flex gap-2">
            <button onClick={editId !== null ? () => handleUpdate(editId) : handleCreate} className="flex items-center gap-1 px-4 py-2 bg-green-500 text-white rounded-xl text-sm"><Check className="w-4 h-4" />保存</button>
            <button onClick={resetForm} className="flex items-center gap-1 px-4 py-2 bg-slate-300 dark:bg-slate-600 rounded-xl text-sm"><X className="w-4 h-4" />取消</button>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            <tr>
              <th className="text-left p-3">Name</th><th className="text-left p-3">Type</th><th className="text-left p-3">Version</th><th className="text-left p-3">Enabled</th><th className="text-right p-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {templates.map(t => (
              <tr key={t.id} className="hover:bg-slate-50 dark:hover:bg-slate-750">
                <td className="p-3 font-medium">{t.name}</td>
                <td className="p-3 text-slate-500">{t.prompt_type}</td>
                <td className="p-3">v{t.version}</td>
                <td className="p-3">{t.enabled ? '✅' : '❌'}</td>
                <td className="p-3 text-right flex justify-end gap-2">
                  <button onClick={() => startEdit(t)} className="p-1.5 text-slate-400 hover:text-primary-500"><Edit3 className="w-4 h-4" /></button>
                  <button onClick={() => handleDelete(t.id)} className="p-1.5 text-slate-400 hover:text-red-500"><Trash2 className="w-4 h-4" /></button>
                </td>
              </tr>
            ))}
            {templates.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-slate-400">暂无模板</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}