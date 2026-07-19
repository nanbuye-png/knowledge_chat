import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Shield, ShieldAlert, BookOpen, Users, Building2, Globe, Lock, Search } from 'lucide-react'
import * as kbApi from '../../api/knowledgeBases'
import type { KnowledgeBase } from '../../api/knowledgeBases'

type AccessLevel = 'public' | 'organization' | 'department' | 'private'

const ACCESS_LEVELS: { key: AccessLevel; label: string; icon: typeof Globe; desc: string }[] = [
  { key: 'public', label: '公开', icon: Globe, desc: '所有用户可访问' },
  { key: 'organization', label: '组织', icon: Building2, desc: '组织成员可访问' },
  { key: 'department', label: '部门', icon: Users, desc: '指定部门可访问' },
  { key: 'private', label: '私有', icon: Lock, desc: '仅本人可访问' },
]

export default function KnowledgeACLPage() {
  const [kbList, setKbList] = useState<KnowledgeBase[]>([])
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAccess, setSelectedAccess] = useState<AccessLevel>('private')

  const fetchKbList = useCallback(async () => {
    try {
      setError(null)
      const list = await kbApi.listKnowledgeBases()
      setKbList(list)
    } catch (err: any) {
      setError(err.message || '知识库列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchKbList() }, [fetchKbList])

  const handleSelectKb = (kb: KnowledgeBase) => {
    setSelectedKb(kb)
    setSelectedAccess('private')
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-500">
        <p className="mb-4">{error}</p>
        <button onClick={fetchKbList} className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600">重新加载</button>
      </div>
    )
  }

  const selected = selectedKb

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Shield className="w-6 h-6 text-purple-500" />
          知识库权限
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">管理知识库访问控制</p>
      </motion.div>

      {/* KB Selector */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">选择知识库</label>
        <div className="relative max-w-md">
          <BookOpen className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <select
            value={selected?.id ?? ''}
            onChange={e => {
              const kb = kbList.find(k => k.id === Number(e.target.value))
              if (kb) handleSelectKb(kb)
            }}
            className="w-full pl-9 pr-8 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/30"
          >
            <option value="">-- 请选择 --</option>
            {kbList.map(kb => (
              <option key={kb.id} value={kb.id}>{kb.name}</option>
            ))}
          </select>
        </div>
      </motion.div>

      {selected ? (
        <>
          {/* Access Level Selection */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="mb-8">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">
              {selected.name} — 访问级别
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {ACCESS_LEVELS.map(al => {
                const Icon = al.icon
                const isSelected = selectedAccess === al.key
                return (
                  <button
                    key={al.key}
                    onClick={() => setSelectedAccess(al.key)}
                    className={`p-4 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 shadow-sm'
                        : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600'
                    }`}
                  >
                    <Icon className={`w-5 h-5 mb-2 ${isSelected ? 'text-primary-500' : 'text-slate-400'}`} />
                    <p className={`text-sm font-medium ${isSelected ? 'text-primary-700 dark:text-primary-300' : 'text-slate-700 dark:text-slate-300'}`}>{al.label}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{al.desc}</p>
                  </button>
                )
              })}
            </div>
          </motion.div>

          {/* Permissions Table Placeholder */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">成员权限</h2>
            <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-10 text-center text-slate-400">
              <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p>功能待后端支持</p>
              <p className="text-xs mt-1">后端 ACL 模型已存在，暂无 API 端点</p>
            </div>
          </motion.div>
        </>
      ) : (
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-16 text-center text-slate-400">
          <BookOpen className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>请选择一个知识库查看权限设置</p>
        </div>
      )}
    </div>
  )
}