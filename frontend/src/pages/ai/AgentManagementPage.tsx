import { motion } from 'framer-motion'
import { Bot, Plus } from 'lucide-react'
import PlannedNotice from '../../components/common/PlannedNotice'

/**
 * AI Agent 管理页。
 *
 * 审计 §4：本页原先用 hardcoded ``placeholderAgents`` 假数据渲染表格
 * （"知识问答助手 / agnes-2.5-flash / 活跃"），看起来像"已实现"，实际后端
 * 根本没有 ``/api/agents``。现在改为显式的 Planned 标注，假数据已删除。
 *
 * 真实可用的只有工具层：``GET /api/tools``、``POST /api/tools/{tool_name}/invoke``
 * （见 ``/ai/tools`` 页与 ``backend/app/services/tools``）。
 */
export default function AgentManagementPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Bot className="w-6 h-6 text-violet-500" />AI Agents
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI Agent 管理</p>
        </div>
        <button disabled className="flex items-center gap-2 px-4 py-2 bg-primary-500/50 text-white text-sm rounded-xl cursor-not-allowed">
          <Plus className="w-4 h-4" />新建 Agent
        </button>
      </motion.div>

      <PlannedNotice
        feature="AI Agent 编排"
        reason="后端不存在 /api/agents（无模型、无路由、无服务）；本页此前渲染的是前端硬编码的假数据，已删除。README 中同一功能的措辞已同步为 Planned。"
        available="当前真实可用的是工具层：GET /api/tools 列出工具，POST /api/tools/{tool_name}/invoke 调用（kb_search / calculator）。"
      />
    </div>
  )
}
