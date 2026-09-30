import apiClient from './client'

/**
 * Agent API 客户端（审计 §4：Agent 的最小真实路径）。
 *
 * 对应后端 `backend/app/api/agents.py`（本文件是**真实实现**的客户端，不再是
 * 那个打 404 的空壳客户端 —— 空壳版本已随 `AgentStudioPage` 一并删除）：
 *
 *   GET    /api/agents                    → 我的 Agent 列表
 *   POST   /api/agents                    → 创建
 *   GET    /api/agents/{id}               → 详情
 *   PUT    /api/agents/{id}               → 部分更新
 *   DELETE /api/agents/{id}               → 删除
 *   POST   /api/agents/{id}/execute       → 执行（回答 + 完整执行轨迹）
 *
 * Workflow 的客户端（原 `api/workflows.ts`）指向的后端仍然**不存在**，已删除；
 * `/ai/workflows` 是带 Planned 标注的页面，不要恢复那个客户端。
 */

export interface Agent {
  id: number
  user_id: number
  name: string
  description: string | null
  system_prompt: string | null
  knowledge_base_id: number | null
  model_id: number | null
  tools: string[]
  max_tool_calls: number
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface AgentPayload {
  name: string
  description?: string | null
  system_prompt?: string | null
  knowledge_base_id?: number | null
  model_id?: number | null
  tools?: string[]
  max_tool_calls?: number
  enabled?: boolean
}

export interface AgentStep {
  tool: string
  ok: boolean
  output?: Record<string, any> | null
  error?: { code: string; message: string } | null
  elapsed_ms: number
}

export interface AgentExecuteResult {
  agent_id: number
  agent_name: string
  query: string
  answer: string
  /** llm = 模型生成；tools_only = 工具结果直接汇总（未绑定模型） */
  answer_mode: 'llm' | 'tools_only'
  model: string | null
  plan: string[]
  steps: AgentStep[]
  completed: number
  aborted: boolean
  max_tool_calls: number
  citations: Record<string, any>[]
  snippets: Record<string, any>[]
  warnings: string[]
  elapsed_ms: number
}

export async function listAgents(): Promise<Agent[]> {
  const { data } = await apiClient.get('/agents')
  return data
}

export async function createAgent(payload: AgentPayload): Promise<Agent> {
  const { data } = await apiClient.post('/agents', payload)
  return data
}

export async function updateAgent(
  agentId: number,
  payload: Partial<AgentPayload>
): Promise<Agent> {
  const { data } = await apiClient.put(`/agents/${agentId}`, payload)
  return data
}

export async function deleteAgent(agentId: number): Promise<void> {
  await apiClient.delete(`/agents/${agentId}`)
}

export async function executeAgent(
  agentId: number,
  query: string,
  topK?: number
): Promise<AgentExecuteResult> {
  const { data } = await apiClient.post(`/agents/${agentId}/execute`, {
    query,
    ...(topK ? { top_k: topK } : {}),
  })
  return data
}
