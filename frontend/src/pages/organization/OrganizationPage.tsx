import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Building2, Users, Shield, Settings, BarChart3, Key, TreePine, Layers } from 'lucide-react'
import * as orgApi from '../../api/organizations'
import type { Organization } from '../../api/organizations'

const modules = [
  { label: '成员管理', icon: Users, path: '/organization/members', desc: '管理组织成员与角色', color: 'text-blue-500' },
  { label: '部门管理', icon: TreePine, path: '/organization/departments', desc: '组织部门与分组', color: 'text-emerald-500' },
  { label: '权限控制', icon: Shield, path: '/knowledge/acl', desc: '知识库访问权限', color: 'text-purple-500' },
  { label: '用量监控', icon: BarChart3, path: '/quota', desc: 'API 调用与资源使用', color: 'text-amber-500' },
  { label: '组织配置', icon: Settings, path: '/admin/system', desc: '组织级别系统设置', color: 'text-orange-500' },
  { label: '模型管理', icon: Layers, path: '/organization/models', desc: '组织级模型配置', color: 'text-indigo-500' },
]

export default function OrganizationPage() {
  const navigate = useNavigate()
  const [org, setOrg] = useState<Organization | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchOrg = useCallback(async () => {
    try {
      const res = await orgApi.listOrganizations(0, 1)
      if (res.items.length > 0) setOrg(res.items[0])
    } catch {
      // No org yet — silent
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchOrg() }, [fetchOrg])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
          <Building2 className="w-7 h-7 text-emerald-500" />
          Organization Console
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1 ml-10">企业管理空间</p>
      </motion.div>

      {/* Org info card */}
      {!loading && org && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl p-5 bg-white dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 mb-8"
        >
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">组织信息</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-slate-400 mb-1">名称</p>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{org.name}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">标识</p>
              <p className="text-sm font-mono text-slate-600 dark:text-slate-300">{org.slug}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">状态</p>
              <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                org.is_active ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-700'
              }`}>
                {org.is_active ? '正常' : '已禁用'}
              </span>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">创建时间</p>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {org.created_at ? new Date(org.created_at).toLocaleDateString('zh-CN') : '-'}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Modules grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((mod, i) => (
          <motion.button
            key={mod.path}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            onClick={() => navigate(mod.path)}
            className="text-left p-6 rounded-2xl bg-white dark:bg-slate-800 
                       border border-slate-200 dark:border-slate-700
                       hover:shadow-lg hover:border-primary-300 dark:hover:border-primary-600
                       transition-all duration-200"
          >
            <mod.icon className={`w-8 h-8 ${mod.color} mb-3`} />
            <h3 className="font-semibold text-slate-800 dark:text-white">{mod.label}</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{mod.desc}</p>
          </motion.button>
        ))}
      </div>
    </div>
  )
}