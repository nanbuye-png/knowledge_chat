import apiClient from './client'

/**
 * 后端支持的 Provider 规范键（`app/core/config.py::LLM_PROVIDERS`）。
 *
 * 规范键与厂商品牌名、模型 ID（`agnes-2.5-flash`、`apihub.agnes-ai.com`）保持一致：
 * `agnes`。历史代码里的 `agens` 曾与品牌名不一致，手工填写对不上就会在运行期变成
 * Agent 的「Agent 生成回答失败」——所以这里同时提供 `normalizeProvider()`，
 * 前端提交前先归一，界面再给出显式提示。
 */
export const LLM_PROVIDERS: readonly string[] = ['deepseek', 'agnes']

/** Provider 别名表（与后端 `PROVIDER_ALIASES` 保持一致；`agens` 为历史拼写）。 */
const PROVIDER_ALIASES: Record<string, string> = {
  agens: 'agnes',
  agness: 'agnes',
  'agnes-ai': 'agnes',
  agnesai: 'agnes',
  'deep-seek': 'deepseek',
  'deepseek-ai': 'deepseek',
}

/** 把用户输入的 Provider 收敛为规范键（去空白 / 小写 / 解析别名）。 */
export function normalizeProvider(name: string): string {
  const key = (name || '').trim().toLowerCase()
  return PROVIDER_ALIASES[key] ?? key
}

/** 该 Provider 是否为后端支持的规范键。 */
export function isSupportedProvider(name: string): boolean {
  return LLM_PROVIDERS.includes(normalizeProvider(name))
}

/** 各 Provider 的常用模型名（与后端 `KNOWN_MODELS` 对齐，仅用于表单建议）。 */
export const PROVIDER_MODEL_SUGGESTIONS: Record<string, string[]> = {
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  agnes: ['agnes-2.0-flash', 'agnes-2.5-flash', 'agnes-2.5-pro', 'agnes-3.0-flash'],
}

export interface LLMModel {
  id: number
  name: string
  provider: string
  model_name: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface LLMModelCreate {
  name: string
  provider: string
  model_name: string
}

export interface LLMModelUpdate {
  name?: string
  provider?: string
  model_name?: string
  enabled?: boolean
}

export async function listModels(): Promise<LLMModel[]> {
  const { data } = await apiClient.get('/llm-models')
  return data
}

export async function getModel(id: number): Promise<LLMModel> {
  const { data } = await apiClient.get(`/llm-models/${id}`)
  return data
}

export async function createModel(model: LLMModelCreate): Promise<LLMModel> {
  const { data } = await apiClient.post('/llm-models', model)
  return data
}

export async function updateModel(id: number, model: LLMModelUpdate): Promise<LLMModel> {
  const { data } = await apiClient.put(`/llm-models/${id}`, model)
  return data
}

export async function deleteModel(id: number): Promise<void> {
  await apiClient.delete(`/llm-models/${id}`)
}