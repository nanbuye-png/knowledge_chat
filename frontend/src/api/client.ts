import axios from 'axios'

/**
 * 从后端错误响应体中提取可读的错误信息。
 *
 * 后端统一错误契约（backend/app/core/exceptions.py）：
 *   {"code": "HTTP_ERROR" | "VALIDATION_ERROR" | ..., "message": "..."}
 * FastAPI 原生请求校验失败（422）仍为：{"detail": [{loc, msg, type}]}
 */
export function extractErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null

  const payload = data as {
    message?: unknown
    detail?: unknown
    error?: { message?: unknown }
  }
  const candidate = payload.message ?? payload.detail ?? payload.error?.message

  if (typeof candidate === 'string' && candidate.trim()) {
    return candidate.trim()
  }

  // FastAPI 422：detail 为错误对象数组，拼接其 msg 字段
  if (Array.isArray(candidate)) {
    const messages = candidate
      .map((item) =>
        typeof item === 'string' ? item : (item as { msg?: unknown })?.msg
      )
      .filter((msg): msg is string => typeof msg === 'string' && msg.trim().length > 0)

    if (messages.length) return messages.join('；')
  }

  return null
}

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: attach JWT token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Log full error details to console for debugging
    console.error('API Error:', {
      url: error.config?.url,
      method: error.config?.method,
      status: error.response?.status,
      data: error.response?.data,
      message: error.message,
    })

    let message: string | undefined = extractErrorMessage(error.response?.data) ?? undefined

    // Provide more specific error messages based on HTTP status
    if (!message) {
      if (error.response) {
        const status = error.response.status
        const contentType = String(error.response.headers?.['content-type'] ?? '')
        if (status === 401) message = 'API 密钥未配置或无效，请在 .env 文件中设置有效的 AGENS_API_KEY（或 DEEPSEEK_API_KEY）'
        else if (status === 402) message = 'API 余额不足，请检查当前 LLM Provider（Agens / DeepSeek）的账户余额'
        else if (status === 422) message = '请求参数有误，请检查输入'
        else if (status === 429) message = '请求过于频繁，请稍后重试'
        else if (status >= 500) {
          // 后端 500 一定返回 JSON 错误体（已被 extractErrorMessage 取出）。
          // 走到这里且是 text/plain，说明是 Vite 开发代理连不上后端（响应体为空）：
          // 这是本地开发最常见的"请求失败"原因。
          message = contentType.includes('text/plain')
            ? '无法连接到后端服务，请先启动后端：cd backend 后执行 uvicorn app.main:app --reload --port 8000'
            : '服务器内部错误，请稍后重试'
        }
        else message = `请求失败 (HTTP ${status})`
      } else if (error.code === 'ECONNABORTED') {
        message = '请求超时，请检查网络连接'
      } else if (error.message?.includes('Network Error')) {
        message = '无法连接到服务器，请确保后端服务已启动（端口 8000）'
      } else {
        message = error.message || '网络请求失败，请稍后重试'
      }
    }

    return Promise.reject(new Error(message))
  }
)

export default apiClient