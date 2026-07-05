import axios from 'axios'

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

    let message = error.response?.data?.detail
      || error.response?.data?.error?.message

    // Provide more specific error messages based on HTTP status
    if (!message) {
      if (error.response) {
        const status = error.response.status
        if (status === 401) message = 'API 密钥未配置或无效，请在 .env 文件中设置有效的 DEEPSEEK_API_KEY'
        else if (status === 402) message = 'API 余额不足，请检查 DeepSeek 账户余额'
        else if (status === 422) message = '请求参数有误，请检查输入'
        else if (status === 429) message = '请求过于频繁，请稍后重试'
        else if (status >= 500) message = '服务器内部错误，请稍后重试'
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