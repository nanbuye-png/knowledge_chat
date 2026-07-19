import { useEffect, useState } from 'react'
import { Cpu, ToggleRight, ToggleLeft } from 'lucide-react'
import LoadingState from '../../../components/common/LoadingState'
import EmptyState from '../../../components/common/EmptyState'
import { listModels, type LLMModel } from '../../../api/models'

export default function OrganizationModelsPage() {
  const [models, setModels] = useState<LLMModel[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listModels().then(setModels).catch(() => setModels([])).finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState text="加载可用模型..." />

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-3">
        <Cpu className="w-6 h-6 text-purple-500" />
        Available Models
      </h1>

      {models.length === 0 ? (
        <EmptyState icon={Cpu} title="No models available" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {models.filter(m => m.enabled).map((m) => (
            <div key={m.id} className="p-5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
              <div className="flex items-center justify-between mb-2">
                <Cpu className="w-5 h-5 text-purple-500" />
                <span className="flex items-center gap-1 text-xs text-emerald-600"><ToggleRight className="w-3 h-3" /> Active</span>
              </div>
              <h3 className="font-semibold text-slate-800 dark:text-white">{m.name}</h3>
              <p className="text-xs text-slate-400 mt-1">Provider: {m.provider}</p>
              <p className="text-xs text-slate-400 font-mono">{m.model_name}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}