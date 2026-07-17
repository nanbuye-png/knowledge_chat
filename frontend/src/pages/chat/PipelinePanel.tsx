import { motion } from 'framer-motion'
import { Brain, Cpu, Database, Search, Layers, Bot, CheckCircle2, Loader2 } from 'lucide-react'

interface PipelineStatus {
  embedding: 'idle' | 'processing' | 'done'
  retrieval: 'idle' | 'processing' | 'done'
  reranker: 'idle' | 'processing' | 'done'
  llm: 'idle' | 'processing' | 'done'
  agent: 'idle' | 'processing' | 'done'
}

interface Props {
  status?: PipelineStatus
  open: boolean
  onToggle: () => void
}

const DEFAULT_STATUS: PipelineStatus = {
  embedding: 'idle',
  retrieval: 'idle',
  reranker: 'idle',
  llm: 'idle',
  agent: 'idle',
}

const STEPS = [
  { key: 'embedding' as const, label: 'Embedding', icon: Database, desc: 'BGE / OpenAI / Voyage' },
  { key: 'retrieval' as const, label: 'Retrieval', icon: Search, desc: 'Hybrid Search (Vector + BM25)' },
  { key: 'reranker' as const, label: 'Reranker', icon: Layers, desc: 'Score Re-ranking' },
  { key: 'llm' as const, label: 'LLM', icon: Cpu, desc: 'DeepSeek / Agens' },
  { key: 'agent' as const, label: 'Agent', icon: Bot, desc: 'Planner + Tools + Memory' },
]

export default function PipelinePanel({ status = DEFAULT_STATUS, open, onToggle }: Props) {
  return (
    <motion.aside
      initial={false}
      animate={{ width: open ? 240 : 0, opacity: open ? 1 : 0 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="flex-shrink-0 bg-white dark:bg-slate-800 border-l border-slate-200 dark:border-slate-700 overflow-hidden"
    >
      <div className="w-[240px] h-full flex flex-col">
        <div className="p-3 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary-500" />
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">AI Pipeline</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {STEPS.map((step, idx) => {
            const Icon = step.icon
            const stepStatus = status[step.key]
            const isActive = stepStatus === 'processing'
            const isDone = stepStatus === 'done'

            return (
              <div key={step.key} className="relative">
                {idx < STEPS.length - 1 && (
                  <div className="absolute left-3.5 top-8 bottom-0 w-px bg-slate-200 dark:bg-slate-700" />
                )}
                <div className={`flex items-start gap-2.5 p-2 rounded-lg transition-colors
                  ${isActive ? 'bg-primary-50 dark:bg-primary-900/20' : ''}
                  ${isDone ? 'bg-green-50 dark:bg-green-900/10' : ''}
                `}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0
                    ${isActive ? 'bg-primary-500 animate-pulse' : ''}
                    ${isDone ? 'bg-green-500' : ''}
                    ${!isActive && !isDone ? 'bg-slate-200 dark:bg-slate-700' : ''}
                  `}>
                    {isActive ? (
                      <Loader2 className="w-3.5 h-3.5 text-white animate-spin" />
                    ) : isDone ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-white" />
                    ) : (
                      <Icon className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-xs font-medium
                      ${isActive ? 'text-primary-700 dark:text-primary-300' : ''}
                      ${isDone ? 'text-green-700 dark:text-green-300' : ''}
                      ${!isActive && !isDone ? 'text-slate-500 dark:text-slate-400' : ''}
                    `}>
                      {step.label}
                    </p>
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5 truncate">
                      {step.desc}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="p-3 border-t border-slate-200 dark:border-slate-700">
          <div className="text-[10px] text-slate-400 dark:text-slate-500 leading-relaxed">
            <p>Mode: RAG Pipeline</p>
            <p className="mt-0.5">Knowledge Base → Embed → Search → Rerank → Generate</p>
          </div>
        </div>
      </div>
    </motion.aside>
  )
}