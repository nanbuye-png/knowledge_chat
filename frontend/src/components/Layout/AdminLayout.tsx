import { motion } from 'framer-motion'
import { LayoutDashboard, Users, ArrowLeft } from 'lucide-react'
import { useNavigate, useLocation } from 'react-router-dom'

interface AdminLayoutProps {
  children: React.ReactNode
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  const navigate = useNavigate()
  const location = useLocation()

  const navLink = (path: string, label: string, icon: React.ReactNode) => (
    <button
      onClick={() => navigate(path)}
      className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
        location.pathname === path
          ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
          : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
      }`}
    >
      {icon}{label}
    </button>
  )

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 to-slate-100 
                    dark:from-slate-900 dark:to-slate-800 text-slate-800 dark:text-slate-100">
      {/* Admin header */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 dark:bg-slate-900/80 
                   border-b border-slate-200/60 dark:border-slate-700/60"
      >
        <div className="max-w-full mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="p-2 rounded-xl text-slate-400 hover:text-primary-500 
                         hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
              title="返回首页"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 
                            flex items-center justify-center shadow-lg shadow-purple-500/25">
                <span className="text-white text-xs font-bold">A</span>
              </div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-purple-600 to-pink-600 
                           bg-clip-text text-transparent">
                管理后台
              </h1>
            </div>
          </div>

          <nav className="flex items-center gap-2">
            {navLink('/admin', '概览', <LayoutDashboard className="w-4 h-4" />)}
            {navLink('/admin/users', '用户管理', <Users className="w-4 h-4" />)}
          </nav>
        </div>
      </motion.header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}