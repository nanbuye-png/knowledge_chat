import { useNavigate } from 'react-router-dom'
import { ShieldAlert, ArrowLeft } from 'lucide-react'

export default function ForbiddenPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900">
      <ShieldAlert className="w-20 h-20 text-red-400 mb-6" />
      <h1 className="text-4xl font-bold text-slate-800 dark:text-white mb-2">403</h1>
      <p className="text-lg text-slate-500 dark:text-slate-400 mb-8">No Permission</p>
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium
                   bg-primary-500 text-white hover:bg-primary-600 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回首页
      </button>
    </div>
  )
}