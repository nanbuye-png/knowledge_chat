import apiClient from './client'

/**
 * 工具调用 API 客户端（审计 §4）。
 *
 * 对应后端 ``backend/app/api/tools.py``：
 *   GET  /api/tools                     → 工具清单（含 JSON Schema 参数描述）
 *   POST /api/tools/{tool_name}/invoke  → 单次调用（body: { arguments })
 *
 * 这里的工具是 **Agent / Workflow 的执行底座**：`/api/agents/{id}/execute` 与
 * `/api/workflows/{id}/execute` 都走同一份注册表（`backend/app/services/tools`）。
 * Agent 客户端见 `api/agents.ts`，Workflow 客户端见 `api/workflows.ts`。
 */
/**
 * 工具参数（后端 ``BaseTool.json_schema()`` 产出的**标准 JSON Schema**，
 * 可直接喂给 LLM function-calling）。
 *
 * 结构是 ``parameters.properties.<参数名>`` —— 这里曾经被当成
 * ``parameters.<参数名>`` 直接读，于是永远读不到规格（新步骤的默认参数永远是 ``{}``，
 * 保存后执行必得 ``TOOL_INVALID_ARGUMENTS``）。用类型把结构钉住，防止再回归。
 */
export interface ToolParameterSchema {
  type: string
  description?: string
  default?: any
  minimum?: number
  maximum?: number
  maxLength?: number
  enum?: Array<string | number>
}

export interface ToolParameterObjectSchema {
  type: 'object'
  properties: Record<string, ToolParameterSchema>
  required?: string[]
}

export interface ToolInfo {
  name: string
  description: string
  /** 标准 JSON Schema：各参数规格在 ``properties`` 里。 */
  parameters: ToolParameterObjectSchema
  /** 必填参数名（后端把 ``parameters.required`` 平铺了一份，省得前端再取）。 */
  required: string[]
}

export interface ToolListResponse {
  tools: ToolInfo[]
  max_calls_per_request: number
  timeout_seconds: number
}

export interface ToolInvokeResult {
  tool: string
  ok: boolean
  output: Record<string, any>
  elapsed_ms: number
}

export async function listTools(): Promise<ToolListResponse> {
  const { data } = await apiClient.get('/tools')
  return data
}

export async function invokeTool(
  toolName: string,
  args: Record<string, any>
): Promise<ToolInvokeResult> {
  const { data } = await apiClient.post(`/tools/${toolName}/invoke`, {
    arguments: args,
  })
  return data
}
