import { useEffect, useState } from 'react'
import { FileText, Plus, Edit3, Trash2, Eye, RotateCcw, Play, CheckCircle, XCircle } from 'lucide-react'
import LoadingState from '../../../components/common/LoadingState'
import EmptyState from '../../../components/common/EmptyState'
import apiClient from '../../../api/client'
import {
  listPrompts, createPrompt, updatePrompt, deletePrompt,
  getVersions, rollbackPrompt, type PromptTemplate, type PromptVersion, type PromptCreate
} from '../../../api/prompts'

export default function PromptStudioPage() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<PromptTemplate | null>(null)
  const [versions, setVersions] = useState<PromptVersion[]>([])
  const [showEditor, setShowEditor] = useState(false)
  const [editForm, setEditForm] = useState<PromptCreate>({ name: '', prompt_type: 'chat', content: '' })
  const [editId, setEditId] = useState<number | null>(null)
  const [showPlayground, setShowPlayground] = useState(false)
  const [playVars, setPlayVars] = useState('{\n  "question": "",\n  "context": ""\n}')
  const [compiled, setCompiled] = useState('')

  const load = () => {
    setLoading(true)
    listPrompts().then(setPrompts).catch(() => setPrompts([])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const loadVersions = async (id: number) => {
    try {
      const v = await getVersions(id)
      setVersions(v)
    } catch { setVersions([]) }
  }

  const selectPrompt = (p: PromptTemplate) => {
    setSelected(p)
    setShowEditor(false)
    setShowPlayground(false)
    loadVersions(p.id)
  }

  const handleCreate = () => {
    setEditForm({ name: '', prompt_type: 'chat', content: '' })
    setEditId(null)
    setShowEditor(true)
  }

  const handleEdit = (p: PromptTemplate) => {
    setEditForm({ name: p.name, prompt_type: p.prompt_type, content: p.content })
    setEditId(p.id)
    setShowEditor(true)
  }

  const handleSave = async () => {
    if (editId) {
      await updatePrompt(editId, editForm)
    } else {
      await createPrompt(editForm)
    }
    setShowEditor(false)
    setEditId(null)
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此 Prompt？')) return
    await deletePrompt(id)
    if (selected?.id === id) setSelected(null)
    load()
  }

  const handleRollback = async (version: number) => {
    if (!selected || !confirm(`回滚到 v${version}？`)) return
    await rollbackPrompt(selected.id, version)
    selectPrompt(selected)
    load()
  }

  const handleCompile = async () => {
    if (!selected) return
    try {
      let vars = {}
      try { vars = JSON.parse(playVars) } catch { return }
      const { data } = await apiClient.post(`/prompt-templates/${selected.id}/compile`, vars)
      setCompiled(typeof data === 'string' ? data : data.content || data.result || JSON.stringify(data))
    } catch (err: any) {
      setCompiled(err?.response?.data?.detail || 'Compile failed')
    }
  }

  if (loading) return <LoadingState text="加载 Prompt 模板..." />

  return (
    <div className="flex h-full">
      {/* Left: Prompt List */}
      <div className="w-72 flex-shrink-0 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 overflow-y-auto">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h2 className="font-semibold text-sm text-slate-800 dark:text-white">Prompts</h2>
          <button onClick={handleCreate} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Plus className="w-4 h-4" /></button>
        </div>
        {prompts.length === 0 ? (
          <div className="p-4"><EmptyState icon={FileText} title="No prompts" description="点击 + 创建" /></div>
        ) : (
          prompts.map((p) => (
            <button
              key={p.id}
              onClick={() => selectPrompt(p)}
              className={`w-full text-left px-3 py-2.5 border-b border-slate-100 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/50 ${selected?.id === p.id ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}
            >
              <p className="text-sm font-medium text-slate-800 dark:text-white">{p.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-slate-400">{p.prompt_type}</span>
                <span className="text-[10px] text-slate-400">v{p.version}</span>
                {p.is_active ? <CheckCircle className="w-2.5 h-2.5 text-emerald-500" /> : <XCircle className="w-2.5 h-2.5 text-slate-300" />}
              </div>
            </button>
          ))
        )}
      </div>

      {/* Right: Detail */}
      <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900">
        {showEditor ? (
          <div className="p-6">
            <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">{editId ? 'Edit Prompt' : 'New Prompt'}</h2>
            <div className="space-y-3 max-w-2xl">
              <input placeholder="Name" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
              <input placeholder="Type (e.g. chat, rag, title)" value={editForm.prompt_type} onChange={(e) => setEditForm({ ...editForm, prompt_type: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
              <textarea placeholder="Content (use {{variable}} syntax)" value={editForm.content} onChange={(e) => setEditForm({ ...editForm, content: e.target.value })} rows={12}
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500 font-mono" />
              <div className="flex gap-2">
                <button onClick={handleSave} className="px-4 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600">Save</button>
                <button onClick={() => setShowEditor(false)} className="px-4 py-1.5 text-sm rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">Cancel</button>
              </div>
            </div>
          </div>
        ) : selected ? (
          <div className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-800 dark:text-white">{selected.name}</h2>
                <p className="text-xs text-slate-400">v{selected.version} · {selected.prompt_type} · {selected.is_active ? 'Active' : 'Inactive'}</p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => handleEdit(selected)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Edit3 className="w-3.5 h-3.5" /></button>
                <button onClick={() => setShowPlayground(!showPlayground)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Play className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(selected.id)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>

            {/* Content */}
            <div className="mb-6">
              <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2">Content</h3>
              <pre className="p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{selected.content}</pre>
            </div>

            {/* Playground */}
            {showPlayground && (
              <div className="mb-6 p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <h3 className="text-sm font-semibold text-slate-800 dark:text-white mb-3">Playground</h3>
                <textarea value={playVars} onChange={(e) => setPlayVars(e.target.value)} rows={4}
                  className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none mb-2" />
                <button onClick={handleCompile} className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 flex items-center gap-1"><Play className="w-3 h-3" /> Compile</button>
                {compiled && (
                  <pre className="mt-3 p-3 rounded-xl bg-slate-100 dark:bg-slate-700 text-sm font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{compiled}</pre>
                )}
              </div>
            )}

            {/* Versions */}
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2">Versions</h3>
              {versions.length === 0 ? (
                <p className="text-sm text-slate-400">No version history</p>
              ) : (
                <div className="space-y-1">
                  {versions.map((v) => (
                    <div key={v.id} className="flex items-center justify-between p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <div>
                        <span className="text-sm font-medium text-slate-800 dark:text-white">v{v.version}</span>
                        <span className="text-xs text-slate-400 ml-3">{v.created_at ? new Date(v.created_at).toLocaleString() : '--'}</span>
                      </div>
                      <button onClick={() => handleRollback(v.version)} className="flex items-center gap-1 text-xs text-primary-500 hover:text-primary-600">
                        <RotateCcw className="w-3 h-3" /> Rollback
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="p-12"><EmptyState icon={FileText} title="Select a prompt template" description="从左侧列表中选择一个 Prompt" /></div>
        )}
      </div>
    </div>
  )
}