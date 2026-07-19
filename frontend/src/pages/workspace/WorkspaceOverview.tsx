import { useEffect, useState } from 'react'
import { BookOpen, FileText, MessageSquare, Cpu } from 'lucide-react'
import StatCard from '../../components/dashboard/StatCard'
import LoadingState from '../../components/common/LoadingState'
import { useNavigate } from 'react-router-dom'
import { listKnowledgeBases } from '../../api/knowledgeBases'

export default function WorkspaceOverview() {
  const navigate = useNavigate()
  const [kbCount, setKbCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listKnowledgeBases()
      .then((kbs) => setKbCount(kbs.length))
      .catch(() => setKbCount(0))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState text="加载工作空间..." />

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-6">AI Workspace</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div onClick={() => navigate('/workspace')} className="cursor-pointer">
          <StatCard label="知识库" value={kbCount ?? '--'} icon={BookOpen} color="text-emerald-500" bgColor="bg-emerald-50 dark:bg-emerald-900/20" delay={0} />
        </div>
        <StatCard label="文档" value="--" icon={FileText} color="text-blue-500" bgColor="bg-blue-50 dark:bg-blue-900/20" delay={0.05} />
        <StatCard label="会话" value="--" icon={MessageSquare} color="text-purple-500" bgColor="bg-purple-50 dark:bg-purple-900/20" delay={0.1} />
        <StatCard label="Token 使用" value="--" icon={Cpu} color="text-orange-500" bgColor="bg-orange-50 dark:bg-orange-900/20" delay={0.15} />
      </div>

      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-6">
        <h2 className="font-semibold text-slate-800 dark:text-white mb-3">最近活动</h2>
        <p className="text-sm text-slate-400">暂无最近活动记录</p>
      </div>
    </div>
  )
}