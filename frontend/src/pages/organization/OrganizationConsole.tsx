import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Building2, Users, Shield, Settings, BarChart3, Key } from 'lucide-react'

const modules = [
  { label: '成员管理', icon: Users, path: '/organization/members', desc: '管理组织成员与角色', color: 'text-blue-500' },
  { label: '权限控制', icon: Shield, path: '/knowledge/acl', desc: '知识库访问权限', color: 'text-purple-500' },
  { label: '用量监控', icon: BarChart3, path: '/quota', desc: 'API 调用与资源使用', color: 'text-emerald-500' },
  { label: '组织配置', icon: Settings, path: '/admin/system', desc: '组织级别系统设置', color: 'text-orange-500' },
]

/**
 * Organization Console - ADMIN 企业管理空间的主页。
 */
export default function OrganizationConsole() {
  const navigate = useNavigate()

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-3">
          <Building2 className="w-7 h-7 text-emerald-500" />
          Organization Console
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1 ml-10">企业管理空间</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((mod, i) => (
          <motion.button
            key={mod.path}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
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