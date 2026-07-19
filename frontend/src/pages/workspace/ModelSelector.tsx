import { useEffect, useState } from 'react'
import { Cpu, ChevronDown } from 'lucide-react'
import { listModels, type LLMModel } from '../../api/models'
import { useModelStore } from '../../store/model'

export default function ModelSelector() {
  const { models, selectedModel, setSelectedModel, setModels } = useModelStore()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (models.length === 0) {
      listModels().then((list) => {
        setModels(list)
        if (list.length > 0 && !selectedModel) {
          setSelectedModel(list[0])
        }
      }).catch(() => {})
    }
  }, [])

  const enabledModels = models.filter(m => m.enabled)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
      >
        <Cpu className="w-3 h-3" />
        {selectedModel?.name || 'Select Model'}
        <ChevronDown className="w-3 h-3" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full mt-1 w-48 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 py-1 z-20">
            {enabledModels.length === 0 ? (
              <p className="px-3 py-2 text-xs text-slate-400">No models available</p>
            ) : (
              enabledModels.map((m) => (
                <button
                  key={m.id}
                  onClick={() => { setSelectedModel(m); setOpen(false) }}
                  className={`w-full text-left px-3 py-2 text-sm ${selectedModel?.id === m.id ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'}`}
                >
                  <span className="font-medium">{m.name}</span>
                  <span className="text-xs text-slate-400 ml-2">{m.provider}</span>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}