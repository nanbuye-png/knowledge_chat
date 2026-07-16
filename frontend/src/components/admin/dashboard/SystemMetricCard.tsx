interface SystemMetricCardProps {
  title: string
  value: number | null
  unit: string
  icon: React.ReactNode
  color: string
}

export default function SystemMetricCard({ title, value, unit, icon, color }: SystemMetricCardProps) {
  const displayValue = value !== null ? `${value.toFixed(1)}${unit}` : 'N/A'
  const percentage = value !== null ? Math.min(100, Math.max(0, value)) : 0

  return (
    <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50 border border-slate-200/60 dark:border-slate-700/60">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-slate-500 dark:text-slate-400">{title}</p>
        <div className={`p-1.5 rounded-lg bg-gradient-to-br ${color} text-white`}>
          {icon}
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-2">
        {displayValue}
      </p>
      <div className="w-full bg-slate-200 dark:bg-slate-600 rounded-full h-2">
        <div
          className={`h-2 rounded-full bg-gradient-to-r ${color}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}