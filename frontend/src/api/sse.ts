/**
 * SSE 工具 —— 统一前端两条流式链路的解析规则（Phase 3 §5.4）。
 *
 * 后端帧契约（backend/app/api/chat.py、api/knowledge_query.py）：
 *
 *   data: {"token": "纯文本增量"}           → 正文
 *   data: {"token": "{\"type\":\"...\"}"}   → 控制帧（token 内是再序列化的 JSON）
 *   data: [DONE]                            → 结束
 *
 * 控制帧类型：``sources``（含 sources/citations）、``no_result``（拒答）、
 * ``error``（本次回答失败）。
 *
 * 之所以抽出来：chat.ts 与 knowledge.ts 曾各写一遍
 * ``buffer.split('\n')`` 循环，控制帧与错误处理也各写一套，
 * 结果是同一份契约在两条链路上行为不一致（例如错误体只认
 * ``detail/error.message``，漏掉后端统一信封的顶层 ``message``）。
 */
import { extractErrorMessage } from './client'

/** 控制帧（token 内嵌 JSON）的最小结构。 */
export interface ControlFrame {
  type: string
  [key: string]: any
}

/**
 * 解析控制帧。
 *
 * :param token: 已取出的 ``token`` 字段原文（控制帧可能带尾部换行，需 trim）。
 * :returns: 合法控制帧返回对象，正文 token 返回 ``null``。
 */
export function parseControlFrame(token: string): ControlFrame | null {
  const trimmed = token.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && typeof parsed.type === 'string') {
      return parsed as ControlFrame
    }
  } catch {
    // 普通正文里也可能出现 '{'，解析失败即视为正文
  }
  return null
}

/** 处理一帧 ``data:`` 载荷；返回 ``'stop'`` 表示不再继续读取。 */
export type SsePayloadHandler = (payload: string) => 'stop' | void

/**
 * 逐帧消费 SSE 响应体（处理 TCP 半行：buffer + split('\n')）。
 *
 * :param response: fetch 的原始响应（必须是 ok 的响应）。
 * :param handle: 每帧载荷回调；``[DONE]`` 由本函数识别并直接停止。
 * :raises Error: 响应没有可读流时抛出。
 */
export async function readSse(response: Response, handle: SsePayloadHandler): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      if (handle(payload) === 'stop') return
    }
  }
}

/**
 * 从失败响应中提取可读错误信息。
 *
 * 后端统一错误信封是 ``{"code": "RATE_LIMITED", "message": "..."}``
 * （core/exceptions.py），旧代码只读 ``detail`` / ``error.message``，
 * 于是 429/403 的真实原因丢失，只能显示 "HTTP 429"。
 */
export async function readResponseError(response: Response): Promise<string> {
  try {
    const data = await response.json()
    return extractErrorMessage(data) ?? `请求失败 (HTTP ${response.status})`
  } catch {
    return `请求失败 (HTTP ${response.status})`
  }
}
