import { motion } from 'framer-motion'
import { BookOpen, MessageCircle } from 'lucide-react'

interface ModeSwitchProps {
  mode: 'knowledge' | 'chat'
  onToggle: (mode: 'knowledge' | 'chat') => void
}

export default function ModeSwitch({ mode, onToggle }: ModeSwitchProps) {
  return (
    <div className="relative flex items-center bg-slate-100 dark:bg-slate-800 rounded-xl p-1 shadow-inner">
      <motion.button
        onClick={() => onToggle('knowledge')}
        className={`relative z-10 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
          mode === 'knowledge'
            ? 'text-white'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        }`}
        whileTap={{ scale: 0.95 }}
      >
        <BookOpen className="w-4 h-4" />
        <span className="hidden sm:inline">知识库</span>
      </motion.button>

      <motion.button
        onClick={() => onToggle('chat')}
        className={`relative z-10 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
          mode === 'chat'
            ? 'text-white'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        }`}
        whileTap={{ scale: 0.95 }}
      >
        <MessageCircle className="w-4 h-4" />
        <span className="hidden sm:inline">闲聊</span>
      </motion.button>

      {/* Animated background indicator */}
      <motion.div
        className="absolute top-1 bottom-1 rounded-lg bg-gradient-to-r from-primary-500 to-primary-600 shadow-md"
        initial={false}
        animate={{
          left: mode === 'knowledge' ? '4px' : '50%',
          right: mode === 'knowledge' ? '50%' : '4px',
        }}
        transition={{ type: 'spring', stiffness: 500, damping: 35 }}
      />
    </div>
  )
}