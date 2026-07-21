/**
 * Knowledge Query API — RAG 问答。
 * 
 * 基于后端 /api/knowledge 端点。
 */
import apiClient from './client'
import type { SourceReference } from '../types'

export async function queryKnowledge(
  question: string,
  knowledgeBaseId: number,
  history: { role: string; content: string }[] = []
): Promise<{
  answer: string
  sources: SourceReference[]
  has_knowledge: boolean
}> {
  const response = await apiClient.post('/knowledge/query', {
    question,
    knowledge_base_id: knowledgeBaseId,
    history,
  })
  return response.data
}

// SSE streaming for knowledge query
export function createStreamKnowledgeQuery(
  question: string,
  knowledgeBaseId: number,
  onSources: (sources: SourceReference[]) => void,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  conversationId?: number,
): AbortController {
  const controller = new AbortController()

  const token = localStorage.getItem('token')
  fetch('/api/knowledge/query/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, knowledge_base_id: knowledgeBaseId, conversation_id: conversationId }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        let errorMsg = '网络请求失败'
        try {
          const errData = await response.json()
          errorMsg = errData.detail || errData.error?.message || `请求失败 (HTTP ${response.status})`
        } catch {
          errorMsg = `请求失败 (HTTP ${response.status})`
        }
        onError(errorMsg)
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              onDone()
              return
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.token) {
                // Check if it's a control message
                try {
                  const inner = JSON.parse(parsed.token)
                  if (inner.type === 'sources') {
                    onSources(inner.sources)
                    continue
                  }
                  if (inner.type === 'no_result') {
                    onToken(inner.message)
                    onDone()
                    return
                  }
                  if (inner.type === 'error') {
                    onError(inner.message)
                    return
                  }
                } catch {
                  // Regular token
                  onToken(parsed.token)
                }
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || '流式请求失败')
      }
    })

  return controller
}