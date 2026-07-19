import { useState } from 'react'
import { motion } from 'framer-motion'
import { Wrench, Plus, Power, PowerOff, Cpu, Search } from 'lucide-react'

export default function ToolRegistryPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Wrench className="w-6 h-6 text-sky-500" />Tool Registry
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI 工具注册表管理（后端能力待实现）</p>
        </div>
        <button disabled className="flex items-center gap-2 px-4 py-2 bg-primary-500/50 text-white text-sm rounded-xl cursor-not-allowed">
          <Plus className="w-4 h-4" />注册工具
        </button>
      </motion.div>

      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-16 text-center text-slate-400">
        <Wrench className="w-12 h-12 mx-auto mb-3 text-slate-300" />
        <p>Tool 功能待后端支持</p>
        <p className="text-xs mt-1">当前系统无 Agent/Workflow/Tool 后端 API</p>
      </div>
    </div>
  )
}