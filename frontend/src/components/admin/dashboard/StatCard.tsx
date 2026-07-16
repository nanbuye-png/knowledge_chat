import { ReactNode } from 'react'

interface StatCardProps {
  title: string
  value: number | string
  icon: ReactNode
  color: string
  bg: string
  text: string
  delay?: number
}

export default function StatCard({ title, value, icon, color, bg, text, delay = 0 }: StatCardProps) {
  return (
    <div
      className={`rounded-2xl p-5 ${bg} border border-slate-200/60 dark:border-slate-700/60`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-xl bg-gradient-to-br ${color} text-white shadow-lg`}>
          {icon}
        </div>
        <span className="text-3xl font-bold text-slate-800 dark:text-slate-100">
          {value}
        </span>
      </div>
      <p className={`text-xs font-medium ${text}`}>
        {title}
      </p>
    </div>
  )
}