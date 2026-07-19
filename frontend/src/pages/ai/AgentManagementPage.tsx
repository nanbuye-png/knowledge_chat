import { useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Plus, Play, Trash2, Cpu, BookOpen, Settings, Power, PowerOff } from 'lucide-react'

const placeholderAgents = [
  { id: 1, name: '知识问答助手', description: '基于知识库的 RAG 问答 Agent', model: 'agnes-2.0-flash', kb: '默认知识库', status: 'active', updated: '2026-07-19' },
]

export default function AgentManagementPage() {
  const [agents] = useState(placeholderAgents)

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Bot className="w-6 h-6 text-violet-500" />AI Agents
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI Agent 管理（后端能力待实现）</p>
        </div>
        <button disabled className="flex items-center gap-2 px-4 py-2 bg-primary-500/50 text-white text-sm rounded-xl cursor-not-allowed">
          <Plus className="w-4 h-4" />新建 Agent
        </button>
      </motion.div>

      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">名称</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">描述</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">模型</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">知识库</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">状态</th>
                <th className="text-left px-4 py-3 font-medium text-slate-500 text-xs uppercase">更新</th>
                <th className="text-right px-4 py-3 font-medium text-slate-500 text-xs uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {agents.map((a, i) => (
                <motion.tr key={a.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}>
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">{a.name}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{a.description}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">{a.model}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{a.kb}</td>
                  <td className="px-4 py-3"><span className="inline-flex items-center gap-1 text-xs text-green-600"><span className="w-1.5 h-1.5 rounded-full bg-green-500" />活跃</span></td>
                  <td className="px-4 py-3 text-xs text-slate-500">{a.updated}</td>
                  <td className="px-4 py-3 text-right"><span className="text-xs text-slate-400">功能待后端支持</span></td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {agents.length === 0 && <div className="text-center py-16 text-slate-400"><Bot className="w-12 h-12 mx-auto mb-3 text-slate-300" /><p>暂无 Agent</p></div>}
      </div>
    </div>
  )
}