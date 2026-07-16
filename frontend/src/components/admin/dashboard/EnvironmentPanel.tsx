interface EnvironmentPanelProps {
  system: {
    uptime: string | null
    python_version: string | null
    platform: string | null
    timestamp: string | null
  }
}

export default function EnvironmentPanel({ system }: EnvironmentPanelProps) {
  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return 'N/A'
    return new Date(timestamp).toLocaleString('zh-CN')
  }

  return (
    <div className="rounded-2xl p-6 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
      <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
        🖥️ 环境信息
      </h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Python 版本</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
            {system.python_version || 'N/A'}
          </p>
        </div>
        <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">操作系统</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
            {system.platform || 'N/A'}
          </p>
        </div>
        <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">运行时间</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
            {system.uptime || 'N/A'}
          </p>
        </div>
        <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700/50">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">更新时间</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
            {formatTimestamp(system.timestamp)}
          </p>
        </div>
      </div>
    </div>
  )
}