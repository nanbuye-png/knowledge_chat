import type { ElementType } from 'react'

interface EmptyStateProps {
  icon: ElementType
  title: string
  description?: string
}

export default function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Icon className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
      <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
      {description && <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{description}</p>}
    </div>
  )
}