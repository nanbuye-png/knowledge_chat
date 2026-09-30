import apiClient from './client'

/**
 * 工具调用 API 客户端（审计 §4）。
 *
 * 对应后端 ``backend/app/api/tools.py``：
 *   GET  /api/tools                     → 工具清单（含 JSON Schema 参数描述）
 *   POST /api/tools/{tool_name}/invoke  → 单次调用（body: { arguments })
 *
 * 注意：Agent / Workflow 的客户端（``api/agents.ts``、``api/workflows.ts``）
 * 对应的后端**不存在**，那两个页面已标注 Planned，不要把它们当成可用能力。
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
