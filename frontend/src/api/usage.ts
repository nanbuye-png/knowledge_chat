import apiClient from './client'

export interface UsageStats {
  total_calls: number
  total_tokens: number
  avg_latency_ms: number
}

export interface UsageRecord {
  id: number
  user_id: number
  conversation_id: number | null
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  created_at: string
}

export async function getUsageStats(): Promise<UsageStats> {
  const { data } = await apiClient.get('/usage/stats')
  return data
}

export async function getRecentUsage(limit = 20): Promise<UsageRecord[]> {
  const { data } = await apiClient.get('/usage/recent', { params: { limit } })
  return data
}