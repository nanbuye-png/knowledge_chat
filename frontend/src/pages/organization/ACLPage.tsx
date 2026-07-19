import { BookOpen, Shield } from 'lucide-react'

export default function ACLPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-3">
        <Shield className="w-6 h-6 text-purple-500" />
        知识库权限
      </h1>

      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-6">
        <p className="text-sm text-slate-500 mb-4">
          管理知识库的访问权限控制。
        </p>

        <div className="space-y-3">
          {['知识库 A', '知识库 B', '知识库 C'].map((kb) => (
            <div key={kb} className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-700/50">
              <div className="flex items-center gap-3">
                <BookOpen className="w-4 h-4 text-slate-400" />
                <span className="text-sm text-slate-700 dark:text-slate-300">{kb}</span>
              </div>
              <span className="text-xs text-slate-400">权限配置（后续完善）</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}