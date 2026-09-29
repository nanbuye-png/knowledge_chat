/**
 * Knowledge Query API — RAG 问答。
 * 
 * 基于后端 /api/knowledge 端点。
 */
import apiClient from './client'
import { parseControlFrame, readResponseError, readSse } from './sse'
import type { AbstentionInfo, Citation, QueryAnswer, SourceReference } from '../types'

/**
 * 非流式 RAG 问答。
 *
 * 响应契约（schemas/chat.py: QueryResponse）：``abstained=true`` 表示
 * 检索没找到足够依据（正常业务结果，answer 是拒答文案）；``error`` 非空
 * 表示本次回答**失败**（限流/超时），调用方必须区分，不能当模型回答统计。
 */
export async function queryKnowledge(
  question: string,
  knowledgeBaseId: number,
  history: { role: string; content: string }[] = [],
  conversationId: number | null = null
): Promise<QueryAnswer> {
  const response = await apiClient.post('/knowledge/query', {
    question,
    knowledge_base_id: knowledgeBaseId,
    history,
    conversation_id: conversationId,
  })
  return response.data
}

/** 流式回调（控制帧按类型分发）。 */
export interface KnowledgeStreamHandlers {
  /** 引用列表（sources 控制帧） */
  onSources?: (sources: SourceReference[]) => void
  /** 结构化引用（sources 控制帧，§5.5） */
  onCitations?: (citations: Citation[]) => void
  /** 正文增量 */
  onToken?: (token: string) => void
  /** 拒答（no_result 控制帧）：检索无依据，未调用 LLM */
  onAbstention?: (info: AbstentionInfo) => void
  /** 流正常结束 */
  onDone?: () => void
  /** 本次回答失败（error 控制帧 / HTTP 错误） */
  onError?: (error: string) => void
}

/**
 * 流式 RAG 问答（SSE）。
 *
 * 帧契约见 ``api/sse.ts``；``conversationId`` 传入时后端会持久化
 * 用户消息与回答（多轮上下文与历史记录都依赖它）。
 */
export function createStreamKnowledgeQuery(
  question: string,
  knowledgeBaseId: number,
  handlers: KnowledgeStreamHandlers,
  conversationId?: number,
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('token')
  // 控制帧（拒答/错误）已给出终态，不再补发 onDone —— 否则调用方会先收到
  // onError 再收到 onDone，把失败当成正常结束处理。
  let settled = false

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

        switch (frame.type) {
          case 'sources':
            handlers.onSources?.(frame.sources ?? [])
            handlers.onCitations?.(frame.citations ?? [])
            break
          case 'no_result':
            settled = true
            handlers.onAbstention?.({
              abstained: frame.abstained ?? true,
              reason: frame.reason ?? null,
              message: frame.message ?? '',
              details: frame.details,
            })
            return 'stop'
          case 'error':
            settled = true
            handlers.onError?.(frame.message ?? '问答失败，请稍后重试')
            return 'stop'
          default:
            break
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
