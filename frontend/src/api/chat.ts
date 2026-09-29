/**
 * Chat API — 通用 AI 对话（非 RAG）。
 * 
 * 基于后端 /api/chat 端点。
 */
import apiClient from './client'
import { parseControlFrame, readResponseError, readSse } from './sse'

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

/** 流式回调（控制帧按类型分发）。 */
export interface ChatStreamHandlers {
  /** 正文增量 */
  onToken?: (token: string) => void
  /** 流正常结束 */
  onDone?: () => void
  /** 本次回答失败（error 控制帧 / HTTP 错误） */
  onError?: (error: string) => void
}

/**
 * 流式通用对话（SSE）。
 *
 * 帧契约与 RAG 流式一致（见 ``api/sse.ts``）：正文为
 * ``data: {"token": "..."}``，错误走 ``{"type":"error"}`` 控制帧 ——
 * 否则前端会把"无权访问该会话"当成模型回答直接渲染给用户。
 *
 * :param conversationId: 传入时后端持久化用户消息与回答（前端应在
 *     首次发送前先创建会话，见 ChatPage 的懒创建）。
 */
export function createStreamChat(
  message: string,
  history: { role: string; content: string }[],
  handlers: ChatStreamHandlers,
  conversationId: number | null = null
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('token')
  // 错误控制帧已给出终态，不再补发 onDone（避免"失败 + 正常结束"双回调）。
  let settled = false

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
        handlers.onError?.(await readResponseError(response))
        return
      }

      await readSse(response, (payload) => {
        let parsed: { token?: unknown }
        try {
          parsed = JSON.parse(payload)
        } catch {
          return // 非法 JSON 帧：跳过
        }
        if (typeof parsed.token !== 'string') return

        const frame = parseControlFrame(parsed.token)
        if (!frame) {
          handlers.onToken?.(parsed.token)
          return
        }
        if (frame.type === 'error') {
          settled = true
          handlers.onError?.(frame.message ?? '对话失败，请稍后重试')
          return 'stop'
        }
      })
      if (!settled) handlers.onDone?.()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        handlers.onError?.(err.message || '流式请求失败')
      }
    })

  return controller
}
