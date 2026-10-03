import apiClient from './client'

/**
 * Workflow API 客户端（审计 §4：Workflow 的最小真实路径）。
 *
 * 对应后端 `backend/app/api/workflows.py`（**真实实现**，不再是那个打 404 的空壳
 * 客户端 —— 空壳版本已随 `WorkflowStudioPage` 一并删除后又按真实后端重建）：
 *
 *   GET    /api/workflows                   → 我的 Workflow 列表
 *   POST   /api/workflows                   → 创建
 *   GET    /api/workflows/{id}              → 详情
 *   PUT    /api/workflows/{id}              → 部分更新（PATCH 同义）
 *   DELETE /api/workflows/{id}              → 删除
 *   POST   /api/workflows/{id}/execute      → 执行（逐步轨迹 + 跳过/失败原因）
 *
 * 与 Agent 的区别（README 同一口径）：Agent 是"动态规划 + 工具选择 + 循环"，
 * Workflow 是**用户显式声明**的有序步骤 + 条件分支 + 状态传递 + 失败处理。
 * 两者共用同一份工具注册表（见 `api/tools.ts`）。
 */

/** 步骤参数里的占位符：`{{input}}` / `{{steps.<步骤ID>.output.<字段>}}`。 */
export type WorkflowWhen =
  | 'always'
  | 'previous_succeeded'
  | 'previous_failed'
  | 'input_is_math'

export type WorkflowOnError = 'abort' | 'continue'

export interface WorkflowStep {
  id: string
  tool: string
  arguments: Record<string, any>
  when: WorkflowWhen
  on_error: WorkflowOnError
}

export interface Workflow {
  id: number
  user_id: number
  name: string
  description: string | null
  steps: WorkflowStep[]
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface WorkflowPayload {
  name: string
  description?: string | null
  steps: WorkflowStep[]
  enabled?: boolean
}

export interface WorkflowStepResult {
  id: string
  tool: string
  ok: boolean
  skipped: boolean
  skip_reason: string | null
  output?: Record<string, any> | null
  error?: { code: string; message: string } | null
  elapsed_ms: number
}

export interface WorkflowExecuteResult {
  workflow_id: number
  workflow_name: string
  input: string
  steps: WorkflowStepResult[]
  completed: number
  skipped: number
  aborted: boolean
  aborted_at: string | null
  max_steps: number
  warnings: string[]
  elapsed_ms: number
}

export async function listWorkflows(): Promise<Workflow[]> {
  const { data } = await apiClient.get('/workflows')
  return data
}

export async function createWorkflow(payload: WorkflowPayload): Promise<Workflow> {
  const { data } = await apiClient.post('/workflows', payload)
  return data
}

export async function updateWorkflow(
  workflowId: number,
  payload: Partial<WorkflowPayload>
): Promise<Workflow> {
  const { data } = await apiClient.put(`/workflows/${workflowId}`, payload)
  return data
}

export async function deleteWorkflow(workflowId: number): Promise<void> {
  await apiClient.delete(`/workflows/${workflowId}`)
}

export async function executeWorkflow(
  workflowId: number,
  input: string
): Promise<WorkflowExecuteResult> {
  const { data } = await apiClient.post(`/workflows/${workflowId}/execute`, {
    input,
  })
  return data
}
