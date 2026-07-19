import { motion } from 'framer-motion'
import type { ElementType } from 'react'

interface StatCardProps {
  label: string
  value: string | number
  icon: ElementType
  color?: string
  bgColor?: string
  delay?: number
}

export default function StatCard({
  label,
  value,
  icon: Icon,
  color = 'text-primary-500',
  bgColor = 'bg-primary-50 dark:bg-primary-900/20',
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="p-5 rounded-2xl bg-white dark:bg-slate-800 
                 border border-slate-200 dark:border-slate-700
                 hover:shadow-lg transition-shadow duration-200"
    >
      <div className="flex items-center gap-4">
        <div className={`w-12 h-12 rounded-xl ${bgColor} flex items-center justify-center`}>
          <Icon className={`w-6 h-6 ${color}`} />
        </div>
        <div>
          <p className="text-2xl font-bold text-slate-800 dark:text-white">{value}</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
        </div>
      </div>
    </motion.div>
  )
}