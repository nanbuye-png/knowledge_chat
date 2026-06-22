import { motion } from 'framer-motion'
import { Sun, Moon } from 'lucide-react'
import { useThemeStore } from '../../contexts/ThemeContext'

export default function ThemeToggle() {
  const { theme, toggleTheme } = useThemeStore()

  const handleToggle = () => {
    toggleTheme()
    document.documentElement.classList.toggle('dark')
  }

  return (
    <motion.button
      onClick={handleToggle}
      className="relative p-2 rounded-xl bg-white/80 dark:bg-slate-800/80 
                 shadow-sm hover:shadow-md border border-slate-200 dark:border-slate-700
                 transition-all duration-200"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      aria-label={theme === 'light' ? '切换到深色模式' : '切换到亮色模式'}
    >
      <motion.div
        initial={false}
        animate={{ rotate: theme === 'dark' ? 180 : 0 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        {theme === 'light' ? (
          <Sun className="w-5 h-5 text-amber-500" />
        ) : (
          <Moon className="w-5 h-5 text-blue-400" />
        )}
      </motion.div>
    </motion.button>
  )
}