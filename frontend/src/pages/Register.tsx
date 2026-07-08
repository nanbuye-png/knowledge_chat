import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { UserPlus, User, Lock, Mail, ArrowLeft } from 'lucide-react'
import { useAuthStore } from '../store/auth'

export default function Register() {
  const navigate = useNavigate()
  const register = useAuthStore(s => s.register)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

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
      await register(username, password, email || null)
      setSuccess('注册成功！即将跳转到登录页面...')
      setTimeout(() => navigate('/login', { replace: true }), 1500)
    } catch (err: any) {
      setError(err.message || '注册失败')
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
            <UserPlus className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white">
            注册账号
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            创建新账号以使用智问知识库
          </p>
        </div>

        {success && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 
                       rounded-xl px-4 py-3 mb-4 text-sm text-green-700 dark:text-green-300"
          >
            {success}
          </motion.div>
        )}

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

        <form onSubmit={handleSubmit} className="space-y-4">
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

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              邮箱 <span className="text-slate-400">(可选)</span>
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="请输入邮箱地址"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 
                           bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white
                           focus:ring-2 focus:ring-primary-500 focus:border-transparent 
                           outline-none transition-all text-sm"
                disabled={loading}
              />
            </div>
          </div>

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
                placeholder="请输入密码（至少 6 位）"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 dark:border-slate-600 
                           bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white
                           focus:ring-2 focus:ring-primary-500 focus:border-transparent 
                           outline-none transition-all text-sm"
                disabled={loading}
              />
            </div>
          </div>

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
              <UserPlus className="w-4 h-4" />
            )}
            {loading ? '注册中...' : '注册'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400 
                       hover:text-primary-500 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            已有账号？去登录
          </Link>
        </div>
      </motion.div>
    </div>
  )
}