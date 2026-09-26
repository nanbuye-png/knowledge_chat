/**
 * Chat API — 通用 AI 对话（非 RAG）。
 * 
 * 基于后端 /api/chat 端点。
 */
import apiClient from './client'

export async function chatMessage(
  message: string,
  history: { role: string; content: string }[] = [],
  conversationId: number | null = null
): Promise<string> {
  const response = await apiClient.post('/chat/chat', {
    message,
    history,
    conversation_id: conversationId,
  })
  return response.data.answer
}

// SSE streaming for general chat
export function createStreamChat(
  message: string,
  history: { role: string; content: string }[],
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  conversationId: number | null = null
): AbortController {
  const controller = new AbortController()

  const token = localStorage.getItem('token')
  fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
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
                onToken(parsed.token)
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