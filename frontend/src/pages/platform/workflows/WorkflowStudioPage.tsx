import { useEffect, useState } from 'react'
import { Workflow, GitBranch, Plus, Edit3, Trash2, Play, CheckCircle, XCircle, Settings, MessageSquare, Cpu, Search, Bot, Puzzle, ChevronRight } from 'lucide-react'
import LoadingState from '../../../components/common/LoadingState'
import EmptyState from '../../../components/common/EmptyState'
import {
  listWorkflows, createWorkflow, updateWorkflow, deleteWorkflow, executeWorkflow,
  type Workflow as WFType, type WorkflowCreate, type WorkflowNode
} from '../../../api/workflows'

const NODE_TYPES = [
  { type: 'start' as const, label: 'Start', icon: Play, color: 'text-emerald-500' },
  { type: 'end' as const, label: 'End', icon: CheckCircle, color: 'text-red-500' },
  { type: 'prompt' as const, label: 'Prompt', icon: MessageSquare, color: 'text-blue-500' },
  { type: 'llm' as const, label: 'LLM', icon: Cpu, color: 'text-purple-500' },
  { type: 'knowledge' as const, label: 'Knowledge', icon: Search, color: 'text-emerald-500' },
  { type: 'agent' as const, label: 'Agent', icon: Bot, color: 'text-orange-500' },
  { type: 'tool' as const, label: 'Tool', icon: Puzzle, color: 'text-cyan-500' },
]

const NODE_CONFIG_KEYS: Record<string, { label: string; key: string; type: 'text' | 'number' | 'select' }[]> = {
  llm: [
    { label: 'Model', key: 'model', type: 'text' },
    { label: 'Temperature', key: 'temperature', type: 'number' },
  ],
  prompt: [
    { label: 'Template', key: 'template', type: 'text' },
    { label: 'Variables', key: 'variables', type: 'text' },
  ],
  knowledge: [
    { label: 'Knowledge Base ID', key: 'kb_id', type: 'number' },
    { label: 'Top K', key: 'top_k', type: 'number' },
  ],
  agent: [
    { label: 'Agent ID', key: 'agent_id', type: 'number' },
  ],
  tool: [
    { label: 'Tool Name', key: 'tool_name', type: 'text' },
  ],
}

export default function WorkflowStudioPage() {
  const [workflows, setWorkflows] = useState<WFType[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<WFType | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [nodes, setNodes] = useState<WorkflowNode[]>([
    { id: 'start-1', type: 'start', label: 'Start', config: {} },
    { id: 'end-1', type: 'end', label: 'End', config: {} },
  ])
  const [selectedNodeIdx, setSelectedNodeIdx] = useState<number | null>(null)
  const [showPlayground, setShowPlayground] = useState(false)
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<{ result: string; steps: any[] } | null>(null)
  const [executing, setExecuting] = useState(false)

  const load = () => {
    setLoading(true)
    listWorkflows().then(setWorkflows).catch(() => setWorkflows([])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const resetEditor = () => {
    setName('')
    setDesc('')
    setNodes([{ id: 'start-1', type: 'start', label: 'Start', config: {} }, { id: 'end-1', type: 'end', label: 'End', config: {} }])
    setSelectedNodeIdx(null)
  }

  const handleCreate = () => {
    resetEditor()
    setEditId(null)
    setShowEditor(true)
    setShowPlayground(false)
  }

  const handleEdit = (w: WFType) => {
    setName(w.name)
    setDesc(w.description)
    setNodes(w.nodes?.length ? w.nodes : [])
    setEditId(w.id)
    setShowEditor(true)
    setShowPlayground(false)
    setSelectedNodeIdx(null)
  }

  const handleSave = async () => {
    const data: WorkflowCreate = { name, description: desc, nodes, enabled: true }
    if (editId) await updateWorkflow(editId, data)
    else await createWorkflow(data)
    setShowEditor(false)
    resetEditor()
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此 Workflow？')) return
    await deleteWorkflow(id)
    if (selected?.id === id) setSelected(null)
    load()
  }

  const addNode = (type: WorkflowNode['type']) => {
    const template = NODE_TYPES.find(n => n.type === type)
    const newNode: WorkflowNode = { id: `${type}-${Date.now()}`, type, label: template?.label || type, config: {} }
    setNodes(prev => [...prev.slice(0, -1), newNode, ...prev.slice(-1)])
  }

  const removeNode = (idx: number) => {
    setNodes(prev => prev.filter((_, i) => i !== idx))
    setSelectedNodeIdx(null)
  }

  const updateNodeConfig = (key: string, value: any) => {
    if (selectedNodeIdx === null) return
    setNodes(prev => prev.map((n, i) => i === selectedNodeIdx ? { ...n, config: { ...n.config, [key]: value } } : n))
  }

  const handleExecute = async () => {
    if (!selected || !query.trim()) return
    setExecuting(true)
    try {
      const res = await executeWorkflow(selected.id, query)
      setResult(res)
    } catch (err: any) {
      setResult({ result: err?.response?.data?.detail || 'Execution failed', steps: [] })
    } finally {
      setExecuting(false)
    }
  }

  if (loading) return <LoadingState text="加载 Workflows..." />

  return (
    <div className="flex h-full">
      {/* Left: Workflow List */}
      <div className="w-72 flex-shrink-0 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 overflow-y-auto">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h2 className="font-semibold text-sm text-slate-800 dark:text-white flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-primary-500" /> Workflows
          </h2>
          <button onClick={handleCreate} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400"><Plus className="w-4 h-4" /></button>
        </div>
        {workflows.length === 0 ? (
          <div className="p-4"><EmptyState icon={GitBranch} title="No workflows" description="Click + to create" /></div>
        ) : (
          workflows.map((w) => (
            <button
              key={w.id}
              onClick={() => { setSelected(w); setShowEditor(false); setShowPlayground(false); setResult(null) }}
              className={`w-full text-left px-3 py-2.5 border-b border-slate-100 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/50 ${selected?.id === w.id ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}
            >
              <p className="text-sm font-medium text-slate-800 dark:text-white">{w.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-slate-400">{w.description?.slice(0, 30) || 'No description'}</span>
                {w.enabled ? <CheckCircle className="w-2.5 h-2.5 text-emerald-500" /> : <XCircle className="w-2.5 h-2.5 text-slate-300" />}
              </div>
            </button>
          ))
        )}
      </div>

      {/* Right: Detail */}
      <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900">
        {showEditor ? (
          <div className="p-6 max-w-3xl">
            <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">{editId ? 'Edit Workflow' : 'New Workflow'}</h2>

            {/* Basic Info */}
            <div className="mb-6 space-y-3">
              <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
              <textarea placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} rows={2}
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500" />
            </div>

            {/* Node Palette */}
            <div className="mb-4">
              <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Add Node</p>
              <div className="flex flex-wrap gap-2">
                {NODE_TYPES.map(nt => (
                  <button key={nt.type} onClick={() => addNode(nt.type)}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700">
                    <nt.icon className={`w-3 h-3 ${nt.color}`} /> {nt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Node List + Config */}
            <div className="flex gap-4 mb-6">
              {/* Node Pipeline */}
              <div className="flex-1 space-y-2">
                <p className="text-xs font-semibold text-slate-400 uppercase mb-1">Pipeline</p>
                {nodes.map((node, idx) => (
                  <div key={node.id}
                    onClick={() => setSelectedNodeIdx(idx)}
                    className={`flex items-center justify-between p-2.5 rounded-xl cursor-pointer border ${selectedNodeIdx === idx ? 'border-primary-300 bg-primary-50 dark:bg-primary-900/20 dark:border-primary-600' : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800'} hover:border-primary-200`}>
                    <div className="flex items-center gap-2">
                      {(() => { const t = NODE_TYPES.find(n => n.type === node.type); return t ? <t.icon className={`w-3.5 h-3.5 ${t.color}`} /> : null })()}
                      <span className="text-sm text-slate-700 dark:text-slate-300">{node.label}</span>
                    </div>
                    {node.type !== 'start' && node.type !== 'end' && (
                      <button onClick={(e) => { e.stopPropagation(); removeNode(idx) }} className="text-slate-300 hover:text-red-500"><Trash2 className="w-3 h-3" /></button>
                    )}
                  </div>
                ))}
              </div>

              {/* Config Panel */}
              {selectedNodeIdx !== null && (
                <div className="w-64 p-4 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-2 mb-3">
                    <Settings className="w-4 h-4 text-slate-400" />
                    <span className="text-sm font-medium text-slate-800 dark:text-white">Config</span>
                  </div>
                  {NODE_CONFIG_KEYS[nodes[selectedNodeIdx].type] ? (
                    NODE_CONFIG_KEYS[nodes[selectedNodeIdx].type].map(cfg => (
                      <div key={cfg.key} className="mb-2">
                        <label className="text-xs text-slate-400 block mb-0.5">{cfg.label}</label>
                        <input type={cfg.type} value={nodes[selectedNodeIdx].config[cfg.key] || ''}
                          onChange={(e) => updateNodeConfig(cfg.key, cfg.type === 'number' ? Number(e.target.value) : e.target.value)}
                          className="w-full px-2 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none" />
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-400">No configuration for this node type</p>
                  )}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <button onClick={handleSave} className="px-4 py-1.5 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600">Save</button>
              <button onClick={() => setShowEditor(false)} className="px-4 py-1.5 text-sm rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">Cancel</button>
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

            {/* Node Pipeline View */}
            <div className="mb-6">
              <p className="text-xs font-semibold text-slate-400 uppercase mb-2">Pipeline</p>
              <div className="flex flex-wrap gap-2">
                {selected.nodes?.map((node, i) => {
                  const nt = NODE_TYPES.find(n => n.type === node.type)
                  return (
                    <span key={node.id} className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300">
                      {nt && <nt.icon className={`w-3 h-3 ${nt.color}`} />}
                      {node.label}
                      {i < (selected.nodes?.length || 0) - 1 && <ChevronRight className="w-3 h-3 text-slate-300" />}
                    </span>
                  )
                })}
              </div>
            </div>

            {/* Playground */}
            {showPlayground && (
              <div className="mb-6 p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                <h3 className="text-sm font-semibold text-slate-800 dark:text-white mb-3 flex items-center gap-2"><Play className="w-4 h-4 text-primary-500" /> Playground</h3>
                <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Enter input..." rows={3}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none mb-2" />
                <button onClick={handleExecute} disabled={executing || !query.trim()}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 flex items-center gap-1">
                  <Play className="w-3 h-3" /> {executing ? 'Running...' : 'Run Workflow'}
                </button>
                {result && (
                  <div className="mt-3 space-y-3">
                    <div className="p-3 rounded-xl bg-slate-100 dark:bg-slate-700">
                      <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{result.result}</p>
                    </div>
                    {result.steps?.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-slate-400 mb-1">Steps</p>
                        {result.steps.map((s, i) => (
                          <div key={i} className="p-2 mb-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                            <p className="text-xs text-slate-500">Step {i + 1}: {typeof s === 'string' ? s : JSON.stringify(s)}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="p-12"><EmptyState icon={GitBranch} title="Select a Workflow" description="从左侧列表中选择一个 Workflow 或点击 + 创建" /></div>
        )}
      </div>
    </div>
  )
}