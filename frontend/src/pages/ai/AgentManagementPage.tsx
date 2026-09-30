import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Play, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import LoadingState from '../../components/common/LoadingState'
import { listKnowledgeBases, type KnowledgeBase } from '../../api/knowledgeBases'
import { listModels, type LLMModel } from '../../api/models'
import { listTools, type ToolInfo } from '../../api/tools'
import {
  createAgent,
  deleteAgent,
  executeAgent,
  listAgents,
  updateAgent,
  type Agent,
  type AgentExecuteResult,
  type AgentPayload,
} from '../../api/agents'

/**
 * AI Agent 管理页（审计 §4）。
 *
 * 历史问题：本页曾用硬编码 placeholderAgents 假数据渲染表格，后来一度只剩一个
 * Planned 标注。现在后端已落地**最小真实路径**（agents 表 + /api/agents CRUD +
 * /{id}/execute），因此本页打的是真实接口：
 *
 * - 配置：绑定知识库 / 模型 / 工具（工具清单来自 GET /api/tools，不是写死的）；
 * - 执行：调用 POST /api/agents/{id}/execute，并把 answer_mode、逐步 steps、
 *   warnings 原样展示 —— 未绑定模型时页面明确标注"工具结果汇总"，不会把
 *   tools_only 伪装成模型生成。
 *
 * Workflow 仍未实现，页面保持 Planned 标注（见 WorkflowManagementPage）。
 */

const EMPTY_FORM: AgentPayload = {
  name: '',
  description: '',
  system_prompt: '',
  knowledge_base_id: null,
  model_id: null,
  tools: [],
  max_tool_calls: 3,
  enabled: true,
}

export default function AgentManagementPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [models, setModels] = useState<LLMModel[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<AgentPayload>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const [selected, setSelected] = useState<Agent | null>(null)
  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentExecuteResult | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [agentList, kbList, modelList, toolList] = await Promise.all([
        listAgents(),
        listKnowledgeBases().catch(() => [] as KnowledgeBase[]),
        listModels().catch(() => [] as LLMModel[]),
        listTools(),
      ])
      setAgents(agentList)
      setKnowledgeBases(kbList)
      setModels(modelList.filter((model) => model.enabled))
      setTools(toolList.tools)
    } catch (err: any) {
      setError(err?.message || '加载 Agent 失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const startCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setNotice(null)
  }

  const startEdit = (agent: Agent) => {
    setEditingId(agent.id)
    setNotice(null)
    setForm({
      name: agent.name,
      description: agent.description ?? '',
      system_prompt: agent.system_prompt ?? '',
      knowledge_base_id: agent.knowledge_base_id,
      model_id: agent.model_id,
      tools: [...agent.tools],
      max_tool_calls: agent.max_tool_calls,
      enabled: agent.enabled,
    })
    setSelected(agent)
    setResult(null)
  }

  const toggleTool = (name: string) => {
    setForm((current) => {
      const currentTools = current.tools ?? []
      return {
        ...current,
        tools: currentTools.includes(name)
          ? currentTools.filter((item) => item !== name)
          : [...currentTools, name],
      }
    })
  }

  const submit = async () => {
    if (!form.name?.trim()) {
      setError('请填写 Agent 名称')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const payload: AgentPayload = {
        ...form,
        name: form.name.trim(),
        description: form.description || null,
        system_prompt: form.system_prompt || null,
      }
      if (editingId === null) {
        const created = await createAgent(payload)
        setNotice(`已创建 Agent：${created.name}`)
      } else {
        await updateAgent(editingId, payload)
        setNotice('配置已保存')
      }
      setEditingId(null)
      setForm(EMPTY_FORM)
      await load()
    } catch (err: any) {
      setError(err?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (agent: Agent) => {
    setError(null)
    try {
      await deleteAgent(agent.id)
      setNotice(`已删除 Agent：${agent.name}`)
      if (selected?.id === agent.id) {
        setSelected(null)
        setResult(null)
      }
      await load()
    } catch (err: any) {
      setError(err?.message || '删除失败')
    }
  }

  const run = async () => {
    if (!selected || !query.trim()) return
    setRunning(true)
    setRunError(null)
    setResult(null)
    try {
      setResult(await executeAgent(selected.id, query.trim()))
    } catch (err: any) {
      setRunError(err?.message || '执行失败')
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <LoadingState text="加载 Agent 配置..." />


  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6"
      >
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Bot className="w-6 h-6 text-violet-500" />AI Agents
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            真实执行：/api/agents CRUD + /api/agents/{'{id}'}/execute（工具选择 →
            复用工具层超时/次数上限/失败处理）
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 text-sm rounded-xl hover:bg-slate-50"
          >
            <RefreshCw className="w-4 h-4" />刷新
          </button>
          <button
            onClick={startCreate}
            className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600"
          >
            <Plus className="w-4 h-4" />新建 Agent
          </button>
        </div>
      </motion.div>

      {error && (
        <div className="mb-4 rounded-2xl border border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-900/10 p-4 text-sm text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-2xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-900/10 p-4 text-sm text-emerald-700 dark:text-emerald-300">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500">
            我的 Agent（{agents.length}）
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
            {agents.map((agent) => (
              <div
                key={agent.id}
                className={`px-4 py-3 ${selected?.id === agent.id ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <button onClick={() => startEdit(agent)} className="text-left flex-1">
                    <p className="font-medium text-sm text-slate-800 dark:text-slate-100">
                      {agent.name}
                      {!agent.enabled && (
                        <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-500">
                          已停用
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      工具：{agent.tools.length ? agent.tools.join(', ') : '未配置'} ·
                      上限 {agent.max_tool_calls} 次
                    </p>
                    <p className="text-[10px] text-slate-400 mt-1">
                      知识库 {agent.knowledge_base_id ? `#${agent.knowledge_base_id}` : '未绑定'} ·
                      模型 {agent.model_id ? `#${agent.model_id}` : '未绑定（tools_only）'}
                    </p>
                  </button>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => { startEdit(agent); setQuery('') }}
                      title="选中并执行"
                      className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => remove(agent)}
                      title="删除"
                      className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {agents.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-slate-400">
                还没有 Agent，点右上角"新建 Agent"开始配置
              </div>
            )}
          </div>
        </div>


        <div className="lg:col-span-3 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-5">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-4">
            {editingId === null ? '新建 Agent' : `编辑 Agent #${editingId}`}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-xs text-slate-500">名称</span>
              <input
                value={form.name ?? ''}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="例如：门诊问答助手"
                className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-500">说明</span>
              <input
                value={form.description ?? ''}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="用途说明（可选）"
                className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              />
            </label>

            <label className="block">
              <span className="text-xs text-slate-500">绑定知识库</span>
              <select
                value={form.knowledge_base_id ?? ''}
                onChange={(e) =>
                  setForm({
                    ...form,
                    knowledge_base_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              >
                <option value="">不绑定</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-xs text-slate-500">
                绑定 LLM 模型（不绑定则只汇总工具结果）
              </span>
              <select
                value={form.model_id ?? ''}
                onChange={(e) =>
                  setForm({
                    ...form,
                    model_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              >
                <option value="">不绑定（answer_mode=tools_only）</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}（{model.provider}/{model.model_name}）
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block mt-4">
            <span className="text-xs text-slate-500">
              系统提示词（LLM 模式的 system message）
            </span>
            <textarea
              value={form.system_prompt ?? ''}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              rows={3}
              placeholder="例如：只根据给定的知识库片段回答，无法确认时明确说明。"
              className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
            />
          </label>


          <div className="mt-4">
            <span className="text-xs text-slate-500">
              可用工具（来自 GET /api/tools；写死的工具名不会被后端接受）
            </span>
            <div className="mt-2 flex flex-wrap gap-2">
              {tools.map((tool) => {
                const checked = (form.tools ?? []).includes(tool.name)
                return (
                  <button
                    key={tool.name}
                    type="button"
                    onClick={() => toggleTool(tool.name)}
                    title={tool.description}
                    className={`px-3 py-1.5 text-xs rounded-lg border font-mono ${
                      checked
                        ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                        : 'border-slate-300 dark:border-slate-600 text-slate-500'
                    }`}
                  >
                    {tool.name}
                  </button>
                )
              })}
              {tools.length === 0 && (
                <span className="text-xs text-slate-400">后端未注册任何工具</span>
              )}
            </div>
          </div>

          <div className="mt-4 flex items-end gap-4">
            <label className="block">
              <span className="text-xs text-slate-500">单次执行最多调用工具次数</span>
              <input
                type="number"
                min={1}
                max={10}
                value={form.max_tool_calls ?? 3}
                onChange={(e) =>
                  setForm({ ...form, max_tool_calls: Number(e.target.value) || 1 })
                }
                className="mt-1 w-28 text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.enabled ?? true}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              启用
            </label>
            <button
              onClick={submit}
              disabled={saving}
              className="ml-auto flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {saving ? '保存中...' : editingId === null ? '创建' : '保存'}
            </button>
          </div>
        </div>
      </div>



      <div className="mt-6 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-5">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">
          执行{selected ? ` · ${selected.name}` : ''}
        </h3>

        {!selected && (
          <p className="text-sm text-slate-400">
            从左侧选择一个 Agent（或点其播放按钮）后即可真实执行。
          </p>
        )}

        {selected && (
          <>
            <div className="flex items-start gap-3">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={2}
                placeholder="例如：门诊时间是什么时候   /   计算 12*12+1"
                className="flex-1 text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
              />
              <button
                onClick={run}
                disabled={running || !query.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-sky-500 text-white text-sm rounded-xl hover:bg-sky-600 disabled:opacity-50"
              >
                <Play className="w-4 h-4" />{running ? '执行中...' : '执行'}
              </button>
            </div>
            <p className="mt-2 text-[10px] text-slate-400">
              工具：{selected.tools.length ? selected.tools.join(', ') : '未配置'}；
              单次最多 {selected.max_tool_calls} 次调用；未绑定模型时回答由工具结果直接汇总。
            </p>

            {runError && (
              <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">{runError}</p>
            )}


            {result && (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span
                    className={`px-2 py-0.5 rounded font-medium ${
                      result.answer_mode === 'llm'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                    }`}
                  >
                    {result.answer_mode === 'llm'
                      ? `模型生成（${result.model ?? '未知模型'}）`
                      : '工具结果汇总（未绑定模型）'}
                  </span>
                  <span className="text-slate-400">
                    计划 [{result.plan.join(' → ') || '无'}] · 成功 {result.completed} 步 ·
                    {result.aborted ? ' 已中止' : ' 未中止'} · {result.elapsed_ms}ms
                  </span>
                </div>

                <pre className="text-xs leading-relaxed whitespace-pre-wrap bg-slate-50 dark:bg-slate-900 rounded-xl p-3 text-slate-700 dark:text-slate-200">
                  {result.answer}
                </pre>

                {result.steps.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-1">执行轨迹</p>
                    <div className="space-y-1">
                      {result.steps.map((step, index) => (
                        <div
                          key={`${step.tool}-${index}`}
                          className="flex items-center gap-2 text-xs text-slate-500"
                        >
                          <span className="font-mono">{step.tool}</span>
                          <span className={step.ok ? 'text-emerald-600' : 'text-rose-600'}>
                            {step.ok
                              ? '成功'
                              : `失败：${step.error?.code} ${step.error?.message ?? ''}`}
                          </span>
                          <span className="text-slate-400">{step.elapsed_ms}ms</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result.warnings.length > 0 && (
                  <div className="text-xs text-amber-600 dark:text-amber-400">
                    {result.warnings.map((warning, index) => (
                      <p key={index}>· {warning}</p>
                    ))}
                  </div>
                )}

                <p className="text-[10px] text-slate-400">
                  引用 {result.citations.length} 条 · 片段 {result.snippets.length} 个 ·
                  本次上限 {result.max_tool_calls} 次工具调用
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
