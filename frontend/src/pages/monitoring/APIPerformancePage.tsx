import { useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, Clock, Hash, RefreshCw, Server } from 'lucide-react'

export default function APIPerformancePage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Activity className="w-6 h-6 text-rose-500" />API Performance
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">API 接口性能监控</p>
      </motion.div>
      <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-16 text-center text-slate-400">
        <Activity className="w-12 h-12 mx-auto mb-3 text-slate-300" />
        <p>Performance metrics unavailable</p>
        <p className="text-xs mt-1">需要后端 API 请求追踪中间件支持</p>
      </div>
    </div>
  )
}