import { motion } from 'framer-motion'
import { GitBranch, Plus } from 'lucide-react'
import PlannedNotice from '../../components/common/PlannedNotice'

/**
 * Workflow 管理页（审计 §4）。
 *
 * 后端不存在 ``/api/workflows``，本页只做显式的 Planned 标注；
 * README 中同一功能的措辞已同步为 Planned。
 */
export default function WorkflowManagementPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <GitBranch className="w-6 h-6 text-rose-500" />Workflows
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI 工作流管理</p>
        </div>
        <button disabled className="flex items-center gap-2 px-4 py-2 bg-primary-500/50 text-white text-sm rounded-xl cursor-not-allowed">
          <Plus className="w-4 h-4" />新建 Workflow
        </button>
      </motion.div>

      <PlannedNotice
        feature="Workflow 编排"
        reason="后端不存在 /api/workflows（无模型、无路由、无服务），前端旧文案「当前系统无 Agent/Workflow/Tool 后端 API」也不完全准确 —— 工具层是真实的。"
        available="工具层已可用：GET /api/tools（清单）、POST /api/tools/{tool_name}/invoke（调用）。"
      />
    </div>
  )
}