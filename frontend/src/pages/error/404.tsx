import { useNavigate } from 'react-router-dom'
import { FileQuestion, ArrowLeft } from 'lucide-react'

/**
 * 404 页面 —— 路由兜底页。
 *
 * 由 router/index.tsx 中的 <Route path="*" /> 渲染，
 * 用于替代此前访问未定义路径时的整页空白。
 */
export default function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900">
      <FileQuestion className="w-20 h-20 text-primary-500 mb-6" />
      <h1 className="text-4xl font-bold text-slate-800 dark:text-white mb-2">404</h1>
      <p className="text-lg text-slate-500 dark:text-slate-400 mb-8">Page Not Found</p>
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium
                     bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300
                     border border-slate-200 dark:border-slate-700
                     hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          返回上一页
        </button>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium
                     bg-primary-500 text-white hover:bg-primary-600 transition-colors"
        >
          返回首页
        </button>
      </div>
    </div>
  )
}
