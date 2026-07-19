import { useEffect, useState } from 'react'
import { Bot, Plus, Edit3, Trash2, Play, CheckCircle, XCircle, Search, BookOpen, FileText } from 'lucide-react'
import LoadingState from '../../../components/common/LoadingState'
import EmptyState from '../../../components/common/EmptyState'
import { listModels, type LLMModel } from '../../../api/models'
import { listPrompts, type PromptTemplate } from '../../../api/prompts'
import { listKnowledgeBases, type KnowledgeBase } from '../../../api/knowledgeBases'
import {
  listAgents, createAgent, updateAgent, deleteAgent, executeAgent,
  type Agent, type AgentCreate
} from '../../../api/agents'

export default function AgentStudioPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Agent | null>(null)
  const [models, setModels] = useState<LLMModel[]>([])
  const [prompts, setPrompts] = useState<PromptTemplate[]>([])
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])

  // Editor
  const [showEditor, setShowEditor] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<AgentCreate>({ name: '', description: '', model_id: 0, prompt_id: 0, tools: [] })

  // Playground
  const [showPlayground, setShowPlayground] = useState(false)
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<{ response: string; steps: any[]; citations: any[] } | null>(null)
  const [executing, setExecuting] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([
      listAgents().catch(() => []),
      listModels().catch(() => []),
      listPrompts().catch(() => []),
      listKnowledgeBases().catch(() => []),
    ]).then(([a, m, p, k]) => {
      setAgents(a)
      setModels(m.filter(m => m.enabled))
      setPrompts(p.filter(p => p.is_active))
      setKbs(k)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCreate = () => {
    setForm({ name: '', description: '', model_id: models[0]?.id || 0, prompt_id: prompts[0]?.id || 0, tools: [] })
    setEditId(null)
    setShowEditor(true)
    setShowPlayground(false)
  }

  const handleEdit = (a: Agent) => {
    setForm({ name: a.name, description: a.description, model_id: a.model_id, prompt_id: a.prompt_id, knowledge_base_id: a.knowledge_base_id, tools: a.tools || [] })
    setEditId(a.id)
    setShowEditor(true)
    setShowPlayground(false)
  }

  const handleSave = async () => {
    if (editId) await updateAgent(editId, form)
    else await createAgent(form)
    setShowEditor(false)
    setEditId(null)
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此 Agent？')) return
    await deleteAgent(id)
    if (selected?.id === id) setSelected(null)
    load()
  }

  const handleExecute = async () => {
    if (!selected || !query.trim()) return
    setExecuting(true)
    try {
      const res = await executeAgent(selected.id, query)
      setResult(res)
    } catch (err: any) {
      setResult({ response: err?.response?.data?.detail || 'Execution failed', steps: [], citations: [] })
    } finally {
      setExecuting(false)
    }
  }

  const toggleTool = (tool: string) => {
    setForm(prev => ({
      ...prev,
      tools: prev.tools?.includes(tool) ? prev.tools.filter(t => t !== tool) : [...(prev.tools || []), tool],
    }))
  }

  if (loading) return <LoadingState text="加载 Agents..." />

  const availableTools = ['knowledge_search', 'document_search', 'llm_chat']

  return (
    <div className="flex h-full">
      {/* Left: Agent List */}
      <div className="w-72 flex-shrink-0 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 overflow-y-auto">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h2 className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2">
            <Bot className="w-4 h-4 text-primary-500" /> Agents
          </h2>
          <button onClick={handleCreate} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Plus className="w-4 h-4" /></button>
        </div>
        {agents.length === 0 ? (
          <div className="p-4"><EmptyState icon={Bot} title="No agents" description="Click + to create" /></div>
        ) : (
          agents.map((a) => (
            <button
              key={a.id}
              onClick={() => { setSelected(a); setShowEditor(false); setShowPlayground(false); setResult(null) }}
              className={`w-full text-left px-3 py-2.5 border-b border-slate-100 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/50 ${selected?.id === a.id ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}
            >
              <p className="text-sm font-medium text-slate-800 dark:text-white">{a.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-slate-400">{a.description?.slice(0, 30) || 'No description'}</span>
                {a.enabled ? <CheckCircle className="w-2.5 h-2.5 text-emerald-500" /> : <XCircle className="w-2.5 h-2.5 text-slate-300" />}
              </div>
            </button>
          ))
        )}
      </div>

      {/* Right: Detail */}
      <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900">
        {showEditor ? (
          <div className="p-6 max-w-2xl">
            <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">{editId ? 'Edit Agent' : 'New Agent'}</h2>
            <div className="space-y-4">
              {/* Basic */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase mb-1 block">Basic Info</label>
                <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500 mb-2" />
                <textarea placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
              </div>

              {/* AI Config */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase mb-1 block">AI Config</label>
                <select value={form.model_id} onChange={(e) => setForm({ ...form, model_id: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none mb-2">
                  <option value={0}>Select Model</option>
                  {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <select value={form.prompt_id} onChange={(e) => setForm({ ...form, prompt_id: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none">
                  <option value={0}>Select Prompt</option>
                  {prompts.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>

              {/* Knowledge */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase mb-1 block">Knowledge Base</label>
                <select value={form.knowledge_base_id || 0} onChange={(e) => setForm({ ...form, knowledge_base_id: Number(e.target.value) || null })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none">
                  <option value={0}>None</option>
                  {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
                </select>
              </div>

              {/* Tools */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase mb-1 block">Tools</label>
                {availableTools.length === 0 ? (
                  <EmptyState icon={Search} title="No tools available" />
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {availableTools.map(tool => (
                      <button key={tool} onClick={() => toggleTool(tool)}
                        className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${form.tools?.includes(tool) ? 'bg-primary-50 border-primary-300 text-primary-700 dark:bg-primary-900/20 dark:border-primary-600 dark:text-primary-300' : 'border-slate-200 dark:border-slate-600 text-slate-500 hover:border-slate-300'}`}>
                        {tool === 'knowledge_search' ? <BookOpen className="w-3 h-3 inline mr-1" /> : <Search className="w-3 h-3 inline mr-1" />}
                        {tool.replace('_', ' ')}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-2">
                <button onClick={handleSave} className="px-4 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600">Save</button>
                <button onClick={() => setShowEditor(false)} className="px-4 py-1.5 text-sm rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">Cancel</button>
              </div>
            </div>
          </div>
        ) : selected ? (
          <div className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-bold text-slate-800 dark:text-white">{selected.name}</h2>
                <p className="text-sm text-slate-400">{selected.description}</p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => handleEdit(selected)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Edit3 className="w-3.5 h-3.5" /></button>
                <button onClick={() => { setShowPlayground(!showPlayground); setResult(null) }} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Play className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(selected.id)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>

            {/* Config Summary */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <p className="text-xs text-slate-400 mb-1">Model</p>
                <p className="text-sm font-medium text-slate-800 dark:text-white">{models.find(m => m.id === selected.model_id)?.name || '--'}</p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <p className="text-xs text-slate-400 mb-1">Prompt</p>
                <p className="text-sm font-medium text-slate-800 dark:text-white">{prompts.find(p => p.id === selected.prompt_id)?.name || '--'}</p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <p className="text-xs text-slate-400 mb-1">Knowledge Base</p>
                <p className="text-sm font-medium text-slate-800 dark:text-white">{kbs.find(k => k.id === selected.knowledge_base_id)?.name || 'None'}</p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <p className="text-xs text-slate-400 mb-1">Tools</p>
                <div className="flex gap-1 flex-wrap mt-1">
                  {selected.tools?.length ? selected.tools.map(t => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500">{t}</span>
                  )) : <span className="text-sm text-slate-500">None</span>}
                </div>
              </div>
            </div>

            {/* Playground */}
            {showPlayground && (
              <div className="mb-6 p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <h3 className="text-sm font-semibold text-slate-800 dark:text-white mb-3">Playground</h3>
                <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Enter your question..." rows={3}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none mb-2" />
                <button onClick={handleExecute} disabled={executing || !query.trim()}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 flex items-center gap-1">
                  <Play className="w-3 h-3" /> {executing ? 'Executing...' : 'Execute'}
                </button>
                {result && (
                  <div className="mt-3 space-y-3">
                    <div className="p-3 rounded-xl bg-slate-100 dark:bg-slate-700">
                      <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{result.response}</p>
                    </div>
                    {result.steps?.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-slate-400 mb-1">Steps</p>
                        {result.steps.map((s, i) => <p key={i} className="text-xs text-slate-500">→ {typeof s === 'string' ? s : JSON.stringify(s)}</p>)}
                      </div>
                    )}
                    {result.citations?.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-slate-400 mb-1">Citations</p>
                        {result.citations.map((c, i) => <p key={i} className="text-xs text-slate-500">[{i + 1}] {typeof c === 'string' ? c : JSON.stringify(c)}</p>)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="p-12"><EmptyState icon={Bot} title="Select an Agent" description="从左侧列表中选择一个 Agent 或点击 + 创建" /></div>
        )}
      </div>
    </div>
  )
}