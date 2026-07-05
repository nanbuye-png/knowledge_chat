import { motion } from 'framer-motion'
import { Brain, Menu, X, LogOut } from 'lucide-react'
import ThemeToggle from '../UI/ThemeToggle'
import ModeSwitch from '../UI/ModeSwitch'

interface NavbarProps {
  mode: 'knowledge' | 'chat'
  sidebarOpen: boolean
  onToggleMode: (mode: 'knowledge' | 'chat') => void
  onToggleSidebar: () => void
  onLogout: () => void
}

export default function Navbar({ mode, sidebarOpen, onToggleMode, onToggleSidebar, onLogout }: NavbarProps) {
  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 dark:bg-slate-900/80 
                 border-b border-slate-200/60 dark:border-slate-700/60"
    >
      <div className="max-w-full mx-auto px-4 h-16 flex items-center justify-between gap-4">
        {/* Left: Logo + Sidebar toggle */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="p-2 rounded-xl text-slate-500 hover:text-primary-500 
                       hover:bg-primary-50 dark:hover:bg-primary-900/30
                       transition-all duration-200 lg:hidden"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>

          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-purple-600 
                          flex items-center justify-center shadow-lg shadow-primary-500/25">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div className="hidden sm:block">
              <h1 className="text-lg font-bold bg-gradient-to-r from-primary-600 to-purple-600 
                           bg-clip-text text-transparent">
                智问
              </h1>
              <p className="text-[10px] text-slate-400 -mt-0.5">智能知识库</p>
            </div>
          </div>
        </div>

        {/* Center: Mode switch */}
        <div className="hidden md:block">
          <ModeSwitch mode={mode} onToggle={onToggleMode} />
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {/* Mobile mode indicator */}
          <div className="md:hidden">
            <span className={`px-2 py-1 rounded-lg text-xs font-medium ${
              mode === 'knowledge'
                ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
            }`}>
              {mode === 'knowledge' ? '知识库' : '闲聊'}
            </span>
          </div>
          <ThemeToggle />
          {/* Logout button */}
          <button
            onClick={onLogout}
            className="p-2 rounded-xl text-slate-400 hover:text-red-500 
                       hover:bg-red-50 dark:hover:bg-red-900/20
                       transition-all duration-200"
            title="退出登录"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Mobile mode switch below navbar */}
      <div className="md:hidden px-4 pb-3 flex justify-center">
        <ModeSwitch mode={mode} onToggle={onToggleMode} />
      </div>
    </motion.header>
  )
}