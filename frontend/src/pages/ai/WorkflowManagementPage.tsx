import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { GitBranch, Play, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import LoadingState from '../../components/common/LoadingState'
import { listKnowledgeBases, type KnowledgeBase } from '../../api/knowledgeBases'
import {
  listTools,
  type ToolInfo,
  type ToolParameterSchema,
} from '../../api/tools'
import {
  createWorkflow,
  deleteWorkflow,
  executeWorkflow,
  getWorkflowLimits,
  listWorkflows,
  updateWorkflow,
  type Workflow,
  type WorkflowExecuteResult,
  type WorkflowLimits,
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
 *
 * 2026-10 修复（两处真问题）：
 *
 * 1. **步骤一多就保存不了**：布局的 `main` 是 `overflow-hidden`，本页此前既没有
 *    自己的滚动容器、步骤区也不限高 —— 加到第 N 个步骤后"保存编排"被顶出视口且
 *    滚不到；再加就会撞上后端 `WORKFLOW_MAX_STEPS`（默认 5）拿到一句英文 422。
 *    现在：页面自己滚动 + 步骤区内部滚动 + 保存条 sticky 常驻 + 步骤数从
 *    `GET /api/workflows/limits` 取（显示 "N / 上限"，到达上限即禁用"添加步骤"）。
 * 2. **calculator 步骤漏填 `expression` 直接失败**：新步骤此前默认参数是 `{}`，
 *    保存后执行必得 `TOOL_INVALID_ARGUMENTS: 缺少必填参数: expression`。现在按工具
 *    的参数 Schema 预填默认值（必填字符串 → `{{input}}`，如 calculator 的
 *    `expression`、kb_search 的 `query`），并对仍缺失的必填参数在步骤内给出橙色提示；
 *    `kb_search` 的 `knowledge_base_id` 刻意不猜（归属问题，必须手填）。
 * 3. **"预填默认值"从头到尾没生效（真根因）**：`GET /api/tools` 的 `parameters` 是
 *    **标准 JSON Schema**（`{type:"object", properties:{...}, required:[...]}`），本页
 *    此前按扁平结构读 `tool.parameters[参数名]` —— 永远读到 `undefined`。于是新建的每个
 *    步骤参数都是 `{}`：calculator 靠执行器兜底（`expression` 按输入补齐）才跑通，
 *    `kb_search` 则直接 `TOOL_INVALID_ARGUMENTS: 缺少必填参数: query`（"看着配好了"其实
 *    没有）。现在统一从 `parameters.properties` 取规格并由 `ToolParameterSchema` 类型钉住
 *    结构；kb_search 步骤另外给一个**知识库下拉**（`GET /api/knowledge-bases`）让用户
 *    显式选库，不用再手查 ID；执行器与写入口共用同一份"可自动取用参数"清单
 *    （后端 `INPUT_FILLED_ARGUMENTS`），页面提示与后端行为不再各说一套。
 */

interface StepDraft {
  id: string
  tool: string
  when: WorkflowWhen
  onError: WorkflowOnError
  argumentsText: string
}

/** 拿不到 `/limits` 时的兜底步骤上限（与后端默认 WORKFLOW_MAX_STEPS 一致）。 */
const FALLBACK_MAX_STEPS = 5

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

/**
 * 执行器会"按本次输入自动取用"的参数（与后端
 * `app/services/workflow/runner.py::INPUT_FILLED_ARGUMENTS` 同一份清单 —— 保存校验、
 * 执行补齐、页面提示三处是同一个答案）。
 */
const INPUT_FILLED_ARGUMENTS: Record<string, string[]> = {
  calculator: ['expression'],
  kb_search: ['query'],
}

/** 工具各参数的规格：标准 JSON Schema 的 `properties`（不是 `parameters` 本身）。 */
function parameterSchemas(
  tool: ToolInfo | undefined
): Record<string, ToolParameterSchema> {
  return tool?.parameters?.properties ?? {}
}

/** 该工具里"缺失也会按输入自动取用"的参数名。 */
function autoFilledArguments(tool: ToolInfo | undefined): string[] {
  return tool ? (INPUT_FILLED_ARGUMENTS[tool.name] ?? []) : []
}

/**
 * 按工具的参数 Schema 生成默认参数。
 *
 * 必填字符串 → `{{input}}`：`query` / `expression` 这类"要的就是本次输入"的参数
 * 占绝大多数，预填它可以让新步骤保存后直接跑通；数字 / 数组等不猜（例如
 * `kb_search.knowledge_base_id` 是数据归属问题，猜了只会换来一个看不懂的 403 ——
 * 页面改用知识库下拉让用户显式选）。
 */
function defaultArguments(tool: ToolInfo | undefined): Record<string, any> {
  const args: Record<string, any> = {}
  if (!tool) return args
  const schemas = parameterSchemas(tool)
  for (const name of tool.required ?? []) {
    const spec = schemas[name] ?? {}
    if (spec.type === 'string') args[name] = '{{input}}'
    else if (spec.type === 'boolean') args[name] = false
    else if (spec.type === 'array') args[name] = []
    else if (spec.type === 'object') args[name] = {}
  }
  return args
}

function formatArguments(args: Record<string, any>): string {
  return JSON.stringify(args, null, 2)
}

/** 解析草稿里的参数 JSON；不是对象 / 解析失败返回 null（保存时由 buildPayload 报错）。 */
function parseArguments(text: string): Record<string, any> | null {
  try {
    const parsed = JSON.parse(text || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as Record<string, any>
  } catch {
    return null
  }
}

/** 该步骤缺了哪些必填参数（工具 Schema 里 required 但没写）—— 提前提示，别等执行才炸。 */
function missingRequiredArguments(step: StepDraft, tool: ToolInfo | undefined): string[] {
  if (!tool) return []
  const args = parseArguments(step.argumentsText)
  if (!args) return []
  return (tool.required ?? []).filter((name) => !(name in args))
}

/** 参数的中文说明（工具 Schema 的 description），用于提示里给用户上下文。 */
function describeParameter(tool: ToolInfo | undefined, name: string): string {
  const description = parameterSchemas(tool)[name]?.description
  return description ? `（${description}）` : ''
}

/**
 * 缺失必填参数的提示（没有缺失就什么都不渲染）。
 *
 * 分两类说清楚，因为后端就是分两类处理的：
 * - 执行器会按输入自动取用的（`INPUT_FILLED_ARGUMENTS`）→ 留空也能跑通；
 * - 不能自动取用的（如 `kb_search.knowledge_base_id`）→ **保存就会被后端拒绝（400）**，
 *   因为它没法替用户推断（数据归属），页面用知识库下拉让用户显式选。
 */
function renderMissingArguments(step: StepDraft, tool: ToolInfo | undefined) {
  const missing = missingRequiredArguments(step, tool)
  if (missing.length === 0) return null
  const autoFilled = autoFilledArguments(tool)
  const blocking = missing.filter((name) => !autoFilled.includes(name))
  const fillable = missing.filter((name) => autoFilled.includes(name))
  return (
    <p className="mt-1 text-[10px] text-amber-600 dark:text-amber-400">
      {blocking.length > 0 && (
        <>
          缺少必填参数：
          {blocking.map((name) => `${name}${describeParameter(tool, name)}`).join('、')}
          ——它不能按本次输入自动取用，
          <span className="font-medium">保存会被后端拒绝（400）</span>
          ，请显式填写（字符串参数可写 {'{{input}}'} 引用本次输入
          {tool?.name === 'kb_search' ? '，知识库请用上方下拉选择' : ''}
          ）。
        </>
      )}
      {blocking.length > 0 && fillable.length > 0 && ' '}
      {fillable.length > 0 && (
        <>
          {fillable.join('、')} 留空也可以：执行时会按本次输入自动取用
          （补了什么会写进执行结果的 warnings）。
        </>
      )}
    </p>
  )
}

function toDraft(step: WorkflowStep): StepDraft {
  return {
    id: step.id,
    tool: step.tool,
    when: step.when ?? 'always',
    onError: step.on_error ?? 'abort',
    argumentsText: JSON.stringify(step.arguments ?? {}, null, 2),
  }
}

function emptyDraft(index: number, tool: ToolInfo | undefined): StepDraft {
  return {
    id: `step${index + 1}`,
    tool: tool?.name ?? '',
    when: 'always',
    onError: 'abort',
    argumentsText: formatArguments(defaultArguments(tool)),
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
  const [limits, setLimits] = useState<WorkflowLimits | null>(null)
  /** 自己的知识库：kb_search 步骤的 `knowledge_base_id` 用下拉选，不用手查 ID。 */
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])

  const [selected, setSelected] = useState<Workflow | null>(null)
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<WorkflowExecuteResult | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  /** 生效的步骤上限：后端 `/limits` 为准，拿不到才用兜底值。 */
  const maxSteps = limits?.max_steps ?? FALLBACK_MAX_STEPS
  const atStepLimit = steps.length >= maxSteps

  const toolByName = useCallback(
    (toolName: string) => tools.find((tool) => tool.name === toolName),
    [tools]
  )

  /** 新步骤的默认工具：calculator（参数只需 `{{input}}`，保存后即可直接执行）。 */
  const preferredTool = useCallback(
    () => tools.find((tool) => tool.name === 'calculator') ?? tools[0],
    [tools]
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [workflowList, toolList, kbList] = await Promise.all([
        listWorkflows(),
        listTools(),
        // 知识库列表单独兜底：拿不到只是下拉空着，用户仍可手写 ID，不该拖垮整个页面
        listKnowledgeBases().catch(() => [] as KnowledgeBase[]),
      ])
      setWorkflows(Array.isArray(workflowList) ? workflowList : [])
      setTools(toolList.tools ?? [])
      setKnowledgeBases(Array.isArray(kbList) ? kbList : [])
    } catch (err: any) {
      setError(err?.message || '加载 Workflow 失败')
    } finally {
      setLoading(false)
    }
    // 上限单独取：拿不到不影响编排（用 FALLBACK_MAX_STEPS 兜底）
    try {
      setLimits(await getWorkflowLimits())
    } catch {
      setLimits(null)
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
    setSteps([emptyDraft(0, preferredTool())])
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

  /** 切换工具时按新工具的 Schema 重填参数（不同工具的必填参数完全不同，保留旧 JSON 只会误导）。 */
  const changeStepTool = (index: number, toolName: string) => {
    updateStep(index, {
      tool: toolName,
      argumentsText: formatArguments(defaultArguments(toolByName(toolName))),
    })
  }

  /**
   * 该工具里"必填的整数知识库 ID"参数名（现在是 `kb_search.knowledge_base_id`）。
   *
   * 用 Schema 判定而不是写死工具名：将来再加一个同样需要指定知识库的工具，下拉自动出现。
   */
  const knowledgeBaseArgKey = (tool: ToolInfo | undefined): string | null => {
    if (!tool) return null
    const schemas = parameterSchemas(tool)
    for (const name of tool.required ?? []) {
      if (schemas[name]?.type === 'integer' && name.includes('knowledge_base_id')) {
        return name
      }
    }
    return null
  }

  /** 读取步骤参数里某个键的当前值（JSON 非法 / 没这个键时为 undefined）。 */
  const stepArgumentValue = (step: StepDraft, key: string): any => {
    const args = parseArguments(step.argumentsText)
    return args && key in args ? args[key] : undefined
  }

  /** 改一个参数键而保留其它手写内容（`value` 传 undefined 表示删掉该键）。 */
  const setStepArgument = (index: number, key: string, value: any) => {
    setSteps((current) =>
      current.map((step, i) => {
        if (i !== index) return step
        const args = parseArguments(step.argumentsText)
        if (!args) return step
        const next = { ...args }
        if (value === undefined) delete next[key]
        else next[key] = value
        return { ...step, argumentsText: formatArguments(next) }
      })
    )
  }

  const addStep = () => {
    setSteps((current) => {
      if (current.length >= maxSteps) return current
      return [...current, emptyDraft(current.length, preferredTool())]
    })
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
    if (steps.length > maxSteps) {
      setError(
        `步骤数不能超过 ${maxSteps}（后端 settings.WORKFLOW_MAX_STEPS），请先删掉多余的步骤`
      )
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
      const args = parseArguments(step.argumentsText)
      if (!args) {
        setError(`步骤 ${step.id} 的参数必须是合法的 JSON 对象`)
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

  // h-full overflow-y-auto：布局的 main 是 overflow-hidden，本页必须自己做滚动容器，
  // 否则步骤一多，"保存编排"就被顶出视口且滚不到
  return (
    <div className="h-full overflow-y-auto p-6 max-w-7xl mx-auto">
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
          <div className="divide-y divide-slate-100 dark:divide-slate-700/50 max-h-[70vh] overflow-y-auto">
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
              <span className="ml-auto text-slate-400">
                最多 {maxSteps} 步 · 单次输入上限 {limits?.max_input_chars ?? 2000} 字符
              </span>
            </label>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-slate-500">
                步骤（按顺序执行；工具来自 GET /api/tools，不是写死的）
              </p>
              <div className="flex items-center gap-2">
                <span
                  className={`text-[10px] ${
                    atStepLimit
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-slate-400'
                  }`}
                >
                  {steps.length} / {maxSteps} 步
                </span>
                <button
                  onClick={addStep}
                  disabled={atStepLimit}
                  title={
                    atStepLimit
                      ? `单条 Workflow 最多 ${maxSteps} 步（后端 settings.WORKFLOW_MAX_STEPS）`
                      : '添加步骤'
                  }
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Plus className="w-3 h-3" />添加步骤
                </button>
              </div>
            </div>

            {/* 步骤区限高内部滚动：步骤再多也不会把"保存编排"顶出视口 */}
            <div className="mt-3 space-y-3 max-h-[55vh] overflow-y-auto pr-1">
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
                      onChange={(e) => changeStepTool(index, e.target.value)}
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
                  {(() => {
                    const kbKey = knowledgeBaseArgKey(toolByName(step.tool))
                    if (!kbKey) return null
                    const current = stepArgumentValue(step, kbKey)
                    const known = knowledgeBases.some((kb) => kb.id === current)
                    return (
                      <label className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                        知识库（{kbKey}）
                        <select
                          value={current === undefined ? '' : String(current)}
                          onChange={(e) =>
                            setStepArgument(
                              index,
                              kbKey,
                              e.target.value === ''
                                ? undefined
                                : Number(e.target.value)
                            )
                          }
                          className="text-xs px-2 py-1 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
                        >
                          <option value="">（未选择 · 保存会被拒绝）</option>
                          {knowledgeBases.map((kb) => (
                            <option key={kb.id} value={kb.id}>
                              #{kb.id} {kb.name}
                            </option>
                          ))}
                          {current !== undefined && !known && (
                            <option value={String(current)}>
                              #{String(current)}（不在你的知识库列表里）
                            </option>
                          )}
                        </select>
                        {knowledgeBases.length === 0 && (
                          <span className="text-amber-600 dark:text-amber-400">
                            还没有知识库：先到“知识库”页新建一个
                          </span>
                        )}
                      </label>
                    )
                  })()}
                  <p className="mt-1 text-[10px] text-slate-400">
                    参数可用 {'{{input}}'} 与 {'{{steps.<步骤ID>.output.<字段>}}'}
                    引用本次输入与前面步骤的输出（整个值就是一个占位符时保留原始类型）
                  </p>
                  {renderMissingArguments(step, toolByName(step.tool))}
                </div>
              ))}
              {steps.length === 0 && (
                <p className="text-xs text-slate-400">还没有步骤，点"添加步骤"开始编排</p>
              )}
            </div>

            <div className="sticky bottom-0 -mx-5 mt-4 flex flex-wrap items-center gap-3 rounded-b-2xl border-t border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-800/95 px-5 py-3 backdrop-blur">
              <button
                onClick={submit}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white text-sm rounded-xl hover:bg-primary-600 disabled:opacity-50"
              >
                <Save className="w-4 h-4" />{saving ? '保存中...' : '保存编排'}
              </button>
              <span className="text-[10px] text-slate-400">
                {steps.length} / {maxSteps} 步 · 超过上限保存会被拒绝（422）；
                不能自动取用的必填参数（如 kb_search 的知识库）留空同样会被拒绝（400）；
                calculator 的 expression / kb_search 的 query 可以留空（执行时按本次输入取用）
              </span>
            </div>
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
                    placeholder="本次执行的输入，例如：门诊时间是什么时候 / 1+2是多少"
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

