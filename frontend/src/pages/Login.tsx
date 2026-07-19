import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { LogIn, User, Lock } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { redirectByRole } from '../router/roleRouter'

export default function Login() {
  const navigate = useNavigate()
  const { login, fetchUser, isAuthenticated } = useAuthStore()

  // Already logged in → redirect based on role
  if (isAuthenticated && localStorage.getItem('token')) {
    const userState = useAuthStore.getState().userState
    if (userState) {
      navigate(redirectByRole(userState.role), { replace: true })
    } else {
      navigate('/', { replace: true })
    }
    return null
  }

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码')
      return
    }
    if (password.length < 6) {
      setError('密码至少 6 位')
      return
    }

    setLoading(true)
    try {
      await login(username, password)
      await fetchUser()
      const userState = useAuthStore.getState().userState
      if (userState) {
        navigate(redirectByRole(userState.role), { replace: true })
      } else {
        navigate('/', { replace: true })
      }
    } catch (err: any) {
      setError(err.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 w-full max-w-md mx-4"
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-purple-500 
                          flex items-center justify-center mb-4 shadow-lg">
            <User className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white">
            智问 · 登录
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            登录以使用智能知识库问答系统
          </p>
        </div>

        {/* Error message */}
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 
                       rounded-xl px-4 py-3 mb-4 text-sm text-red-700 dark:text-red-300"
          >
            {error}
          </motion.div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Username */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              用户名
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 
                           bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white
                           focus:ring-2 focus:ring-primary-500 focus:border-transparent 
                           outline-none transition-all text-sm"
                disabled={loading}
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              密码
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 
                           bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white
                           focus:ring-2 focus:ring-primary-500 focus:border-transparent 
                           outline-none transition-all text-sm"
                disabled={loading}
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-xl font-medium text-white
                       bg-gradient-to-r from-primary-500 to-purple-500 
                       hover:from-primary-600 hover:to-purple-600
                       disabled:opacity-50 disabled:cursor-not-allowed
                       shadow-lg shadow-primary-500/25
                       flex items-center justify-center gap-2 transition-all text-sm"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <LogIn className="w-4 h-4" />
            )}
            {loading ? '登录中...' : '登录'}
          </button>
        </form>

        {/* Register link */}
        <div className="mt-6 text-center">
          <span className="text-sm text-slate-500 dark:text-slate-400">
            没有账号？
          </span>
          <Link
            to="/register"
            className="ml-1 text-sm font-medium text-primary-500 hover:text-primary-600 
                       transition-colors"
          >
            去注册
          </Link>
        </div>
      </motion.div>
    </div>
  )
}