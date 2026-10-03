import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { GitBranch, Play, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import LoadingState from '../../components/common/LoadingState'
import { listTools, type ToolInfo } from '../../api/tools'
import {
  createWorkflow,
  deleteWorkflow,
  executeWorkflow,
  listWorkflows,
  updateWorkflow,
  type Workflow,
  type WorkflowExecuteResult,
  type WorkflowOnError,
  type WorkflowPayload,
  type WorkflowStep,
  type WorkflowWhen,
} from '../../api/workflows'

/**
 * Workflow 管理页（审计 §4）。
 *
 * 历史问题：本页曾是纯 Planned 占位（"后端不存在 /api/workflows"）。现在后端已
 * 落地真实实现（`workflows` 表 + `/api/workflows` CRUD + `/{id}/execute`），
 * 因此本页打的是真实接口：
 *
 * - 编排：有序步骤（工具来自 `GET /api/tools`，不是写死的），每步可设
 *   `when`（条件分支）与 `on_error`（失败策略），参数支持
 *   `{{input}}` / `{{steps.<步骤ID>.output.<字段>}}` 占位符（状态传递）；
 * - 执行：调用 `POST /api/workflows/{id}/execute`，把逐步 `ok` / `skipped` +
 *   `skip_reason` / `error.code` / `warnings` 原样展示 —— 被跳过的步骤与失败的
 *   步骤都不会"看起来跑完了"。
 */

interface StepDraft {
  id: string
  tool: string
  when: WorkflowWhen
  onError: WorkflowOnError
  argumentsText: string
}

const WHEN_OPTIONS: { value: WorkflowWhen; label: string }[] = [
  { value: 'always', label: '总是执行' },
  { value: 'previous_succeeded', label: '上一步成功时' },
  { value: 'previous_failed', label: '上一步失败时' },
  { value: 'input_is_math', label: '输入是数学表达式时' },
]

const ON_ERROR_OPTIONS: { value: WorkflowOnError; label: string }[] = [
  { value: 'abort', label: '中止整条流程' },
  { value: 'continue', label: '继续后续步骤' },
]

function toDraft(step: WorkflowStep): StepDraft {
  return {
    id: step.id,
    tool: step.tool,
    when: step.when ?? 'always',
    onError: step.on_error ?? 'abort',
    argumentsText: JSON.stringify(step.arguments ?? {}, null, 2),
  }
}

function emptyDraft(index: number, tool: string): StepDraft {
  return {
    id: `step${index + 1}`,
    tool,
    when: 'always',
    onError: 'abort',
    argumentsText: '{}',
  }
}

export default function WorkflowManagementPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [steps, setSteps] = useState<StepDraft[]>([])
  const [saving, setSaving] = useState(false)

  const [selected, setSelected] = useState<Workflow | null>(null)
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<WorkflowExecuteResult | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [workflowList, toolList] = await Promise.all([
        listWorkflows(),
        listTools(),
      ])
      setWorkflows(Array.isArray(workflowList) ? workflowList : [])
      setTools(toolList.tools ?? [])
    } catch (err: any) {
      setError(err?.message || '加载 Workflow 失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const startCreate = () => {
    setEditingId(null)
    setName('')
    setDescription('')
    setEnabled(true)
    setSteps([emptyDraft(0, tools[0]?.name ?? '')])
    setNotice(null)
    setSelected(null)
    setResult(null)
  }

  const startEdit = (workflow: Workflow) => {
    setEditingId(workflow.id)
    setName(workflow.name)
    setDescription(workflow.description ?? '')
    setEnabled(workflow.enabled)
    setSteps(workflow.steps.map(toDraft))
    setNotice(null)
    setSelected(workflow)
    setResult(null)
    setRunError(null)
  }

  const updateStep = (index: number, patch: Partial<StepDraft>) => {
    setSteps((current) =>
      current.map((step, i) => (i === index ? { ...step, ...patch } : step))
    )
  }

  const addStep = () => {
    setSteps((current) => [
      ...current,
      emptyDraft(current.length, tools[0]?.name ?? ''),
    ])
  }

  const removeStep = (index: number) => {
    setSteps((current) => current.filter((_, i) => i !== index))
  }

  const buildPayload = (): WorkflowPayload | null => {
    if (!name.trim()) {
      setError('请填写 Workflow 名称')
      return null
    }
    if (steps.length === 0) {
      setError('至少需要一个步骤')
      return null
    }

    const payloadSteps: WorkflowStep[] = []
    for (const [index, step] of steps.entries()) {
      if (!step.id.trim()) {
        setError(`第 ${index + 1} 个步骤缺少 id`)
        return null
      }
      if (!step.tool) {
        setError(`步骤 ${step.id} 还没有选择工具`)
        return null
      }
      let args: Record<string, any>
      try {
        args = JSON.parse(step.argumentsText || '{}')
      } catch {
        setError(`步骤 ${step.id} 的参数不是合法 JSON`)
        return null
      }
      payloadSteps.push({
        id: step.id.trim(),
        tool: step.tool,
        arguments: args,
        when: step.when,
        on_error: step.onError,
      })
    }

    return {
      name: name.trim(),
      description: description || null,
      steps: payloadSteps,
      enabled,
    }
  }

  const submit = async () => {
    setError(null)
    const payload = buildPayload()
    if (!payload) return

    setSaving(true)
    try {
      if (editingId === null) {
        const created = await createWorkflow(payload)
        setNotice(`已创建 Workflow：${created.name}`)
        setEditingId(created.id)
        setSelected(created)
      } else {
        const updated = await updateWorkflow(editingId, payload)
        setNotice('编排已保存')
        setSelected(updated)
      }
      await load()
    } catch (err: any) {
      setError(err?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (workflow: Workflow) => {
    setError(null)
    try {
      await deleteWorkflow(workflow.id)
      setNotice(`已删除 Workflow：${workflow.name}`)
      if (selected?.id === workflow.id) {
        setSelected(null)
        setResult(null)
      }
      if (editingId === workflow.id) setEditingId(null)
      await load()
    } catch (err: any) {
      setError(err?.message || '删除失败')
    }
  }

  const run = async () => {
    if (!selected || !input.trim()) return
    setRunning(true)
    setRunError(null)
    setResult(null)
    try {
      setResult(await executeWorkflow(selected.id, input.trim()))
    } catch (err: any) {
      setRunError(err?.message || '执行失败')
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <LoadingState text="加载 Workflow..." />

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6"
      >
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <GitBranch className="w-6 h-6 text-rose-500" />Workflows
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            真实编排：/api/workflows CRUD + /api/workflows/{'{id}'}/execute（有序步骤 +
            条件分支 + {'{{input}}'} / {'{{steps.<id>.output.*}}'} 状态传递 + 失败策略）
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
            <Plus className="w-4 h-4" />新建 Workflow
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
            我的 Workflow（{workflows.length}）
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700/50 max-h-[560px] overflow-y-auto">
            {workflows.map((workflow) => (
              <div
                key={workflow.id}
                className={`flex items-start gap-2 px-4 py-3 ${
                  selected?.id === workflow.id ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                }`}
              >
                <button onClick={() => startEdit(workflow)} className="flex-1 text-left">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {workflow.name}
                    {!workflow.enabled && (
                      <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500">
                        已停用
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {workflow.steps.length} 步：
                    {workflow.steps.map((step) => step.tool).join(' → ') || '未配置'}
                  </p>
                </button>
                <button
                  onClick={() => remove(workflow)}
                  title="删除"
                  className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
            {workflows.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-slate-400">
                还没有 Workflow，点右上角"新建 Workflow"开始编排
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-3 space-y-6">
          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-5">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-4">
              {editingId === null ? '新建 Workflow' : `编辑 Workflow #${editingId}`}
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="block">
                <span className="text-xs text-slate-500">名称</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：知识库检索 + 计算兜底"
                  className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                />
              </label>
              <label className="block">
                <span className="text-xs text-slate-500">说明</span>
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="用途说明（可选）"
                  className="mt-1 w-full text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                />
              </label>
            </div>

            <label className="mt-4 flex items-center gap-2 text-xs text-slate-500">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="rounded border-slate-300"
              />
              启用（禁用后执行返回 409，而不是空结果）
            </label>

            <div className="mt-5 flex items-center justify-between">
              <p className="text-xs text-slate-500">
                步骤（按顺序执行；工具来自 GET /api/tools，不是写死的）
              </p>
              <button
                onClick={addStep}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50"
              >
                <Plus className="w-3 h-3" />添加步骤
              </button>
            </div>

            <div className="mt-3 space-y-3">
              {steps.map((step, index) => (
                <div
                  key={`${index}-${step.id}`}
                  className="rounded-xl border border-slate-200 dark:border-slate-700 p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-400">#{index + 1}</span>
                    <input
                      value={step.id}
                      onChange={(e) => updateStep(index, { id: e.target.value })}
                      placeholder="步骤 id"
                      className="w-28 font-mono text-xs px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                    />
                    <select
                      value={step.tool}
                      onChange={(e) => updateStep(index, { tool: e.target.value })}
                      className="flex-1 text-xs px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                    >
                      <option value="">（选择工具）</option>
                      {tools.map((tool) => (
                        <option key={tool.name} value={tool.name}>
                          {tool.name}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => removeStep(index)}
                      title="删除该步骤"
                      className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <select
                      value={step.when}
                      onChange={(e) =>
                        updateStep(index, { when: e.target.value as WorkflowWhen })
                      }
                      className="text-xs px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                    >
                      {WHEN_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          条件：{option.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={step.onError}
                      onChange={(e) =>
                        updateStep(index, { onError: e.target.value as WorkflowOnError })
                      }
                      className="text-xs px-2 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                    >
                      {ON_ERROR_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          失败时：{option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <textarea
                    value={step.argumentsText}
                    onChange={(e) =>
                      updateStep(index, { argumentsText: e.target.value })
                    }
                    rows={3}
                    spellCheck={false}
                    placeholder='{"expression": "{{input}}"}'
                    className="mt-2 w-full font-mono text-xs px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                  />
                  <p className="mt-1 text-[10px] text-slate-400">
                    参数可用 {'{{input}}'} 与 {'{{steps.<步骤ID>.output.<字段>}}'}
                    引用本次输入与前面步骤的输出（整个值就是一个占位符时保留原始类型）
                  </p>
                </div>
              ))}
              {steps.length === 0 && (
                <p className="text-xs text-slate-400">还没有步骤，点"添加步骤"开始编排</p>
              )}
            </div>

            <button
              onClick={submit}
              disabled={saving}
              className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />{saving ? '保存中...' : '保存编排'}
            </button>
          </div>

          <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-5">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">
              执行
            </h3>
            {selected ? (
              <>
                <p className="text-xs text-slate-500">
                  {selected.name}（{selected.steps.length} 步：
                  {selected.steps.map((step) => step.tool).join(' → ')}）
                </p>
                <div className="mt-3 flex items-center gap-2">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') run()
                    }}
                    placeholder="本次执行的输入，例如：门诊时间是什么时候 / 1+1"
                    className="flex-1 text-sm px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                  />
                  <button
                    onClick={run}
                    disabled={running || !input.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-sky-500 text-white text-sm rounded-xl hover:bg-sky-600 disabled:opacity-50"
                  >
                    <Play className="w-4 h-4" />{running ? '执行中...' : '执行'}
                  </button>
                </div>

                {runError && (
                  <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">{runError}</p>
                )}

                {result && (
                  <div className="mt-4 space-y-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span
                        className={`px-2 py-0.5 rounded font-medium ${
                          result.aborted
                            ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300'
                            : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        }`}
                      >
                        {result.aborted ? `已中止于 ${result.aborted_at}` : '全部步骤已完成'}
                      </span>
                      <span className="text-slate-400">
                        成功 {result.completed} 步 · 跳过 {result.skipped} 步 · 上限{' '}
                        {result.max_steps} 步 · {result.elapsed_ms}ms
                      </span>
                    </div>

                    <div className="space-y-1">
                      {result.steps.map((step, index) => (
                        <div
                          key={`${step.id}-${index}`}
                          className="flex flex-wrap items-center gap-2 text-xs"
                        >
                          <span className="font-mono text-slate-700 dark:text-slate-200">
                            {step.id}
                          </span>
                          <span className="text-slate-400">{step.tool}</span>
                          {step.skipped ? (
                            <span className="text-amber-600 dark:text-amber-400">
                              已跳过：{step.skip_reason}
                            </span>
                          ) : step.ok ? (
                            <span className="text-emerald-600">成功</span>
                          ) : (
                            <span className="text-rose-600">
                              失败：{step.error?.code} {step.error?.message ?? ''}
                            </span>
                          )}
                          <span className="text-slate-400">{step.elapsed_ms}ms</span>
                        </div>
                      ))}
                    </div>

                    {result.warnings.length > 0 && (
                      <div className="text-xs text-amber-600 dark:text-amber-400">
                        {result.warnings.map((warning, index) => (
                          <p key={index}>· {warning}</p>
                        ))}
                      </div>
                    )}

                    <pre className="text-[10px] leading-relaxed whitespace-pre-wrap bg-slate-50 dark:bg-slate-900 rounded-xl p-3 text-slate-600 dark:text-slate-300 max-h-64 overflow-y-auto">
                      {JSON.stringify(result.steps, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-slate-400">
                从左侧选择一个 Workflow（或先新建并保存）后即可执行
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

