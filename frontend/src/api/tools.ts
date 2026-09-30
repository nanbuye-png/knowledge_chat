import apiClient from './client'

/**
 * 工具调用 API 客户端（审计 §4）。
 *
 * 对应后端 ``backend/app/api/tools.py``：
 *   GET  /api/tools                     → 工具清单（含 JSON Schema 参数描述）
 *   POST /api/tools/{tool_name}/invoke  → 单次调用（body: { arguments })
 *
 * 这里的工具是 **Agent 的执行底座**：``/api/agents/{id}/execute`` 的选择与执行
 * 走同一份注册表（``backend/app/services/tools``）。Agent 客户端见 ``api/agents.ts``。
 *
 * Workflow 的客户端（原 ``api/workflows.ts``）指向的后端**仍不存在**，已删除
 * （审计 §12 P3）；``/ai/workflows`` 只是带 Planned 标注的页面，不要把它当成可用能力。
 */
export interface ToolInfo {
  name: string
  description: string
  parameters: Record<string, any>
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
