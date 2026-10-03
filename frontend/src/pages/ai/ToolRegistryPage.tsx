import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Wrench, Play, RefreshCw } from 'lucide-react'
import LoadingState from '../../components/common/LoadingState'
import {
  listTools,
  invokeTool,
  type ToolInfo,
  type ToolListResponse,
} from '../../api/tools'

/**
 * Tool Registry 页（审计 §4）。
 *
 * 原先是纯静态页（写死"当前系统无 Agent/Workflow/Tool 后端 API"），但工具层现在
 * 是**真实存在**的：本页改为读取 ``GET /api/tools`` 并支持直接试调用
 * （``POST /api/tools/{tool_name}/invoke``），不再有写死的假工具。
 *
 * Agent 已实现最小真实路径（``/ai/agents``，执行器复用本页展示的这份注册表）；
 * Workflow 也已实现（``/ai/workflows``，逐步调用同一份注册表）。
 */
export default function ToolRegistryPage() {
  const [data, setData] = useState<ToolListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selected, setSelected] = useState<ToolInfo | null>(null)
  const [argsText, setArgsText] = useState('{}')
  const [output, setOutput] = useState<string | null>(null)
  const [invokeError, setInvokeError] = useState<string | null>(null)
  const [invoking, setInvoking] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    listTools()
      .then((res) => {
        setData(res)
        setSelected((current) => current ?? res.tools[0] ?? null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleInvoke = async () => {
    if (!selected) return
    setInvoking(true)
    setInvokeError(null)
    setOutput(null)
    try {
      const args = JSON.parse(argsText || '{}')
      const result = await invokeTool(selected.name, args)
      setOutput(JSON.stringify(result.output, null, 2))
    } catch (err: any) {
      setInvokeError(
        err?.message?.includes('JSON')
          ? '参数必须是合法 JSON 对象'
          : err?.message || '调用失败'
      )
    } finally {
      setInvoking(false)
    }
  }

  if (loading) return <LoadingState text="加载工具清单..." />

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
            <Wrench className="w-6 h-6 text-sky-500" />Tool Registry
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            后端已实现的工具（Agent / Workflow 共用这一份注册表）
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 text-sm rounded-xl hover:bg-slate-50">
          <RefreshCw className="w-4 h-4" />刷新
        </button>
      </motion.div>

      {error && (
        <div className="mb-6 rounded-2xl border border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-900/10 p-4 text-sm text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden bg-white dark:bg-slate-800">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500">
            可用工具（{data?.tools.length ?? 0}）
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
            {(data?.tools ?? []).map((tool) => (
              <button
                key={tool.name}
                onClick={() => { setSelected(tool); setArgsText('{}'); setOutput(null); setInvokeError(null) }}
                className={`w-full text-left px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700/50 ${selected?.name === tool.name ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}
              >
                <p className="font-mono text-sm font-medium text-slate-800 dark:text-slate-100">{tool.name}</p>
                <p className="text-xs text-slate-500 mt-1">{tool.description}</p>
                <p className="text-[10px] text-slate-400 mt-1">
                  必填参数：{tool.required.length ? tool.required.join(', ') : '无'}
                </p>
              </button>
            ))}
            {data && data.tools.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-slate-400">后端未注册任何工具</div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-800 p-4">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-3">
            试调用 {selected ? <span className="font-mono text-xs text-slate-500">/{selected.name}</span> : null}
          </h3>

          {selected?.parameters ? (
            <pre className="text-[10px] leading-relaxed bg-slate-50 dark:bg-slate-900 rounded-xl p-3 mb-3 overflow-x-auto text-slate-500">
              {JSON.stringify(selected.parameters, null, 2)}
            </pre>
          ) : null}

          <textarea
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            rows={4}
            spellCheck={false}
            placeholder='{"expression": "(1+2)*3"}'
            className="w-full font-mono text-xs px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100 outline-none"
          />
          <button
            onClick={handleInvoke}
            disabled={invoking || !selected}
            className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 flex items-center gap-1"
          >
            <Play className="w-3 h-3" />{invoking ? '调用中...' : '调用'}
          </button>

          {invokeError && (
            <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">{invokeError}</p>
          )}
          {output && (
            <pre className="mt-3 text-[11px] leading-relaxed bg-slate-50 dark:bg-slate-900 rounded-xl p-3 overflow-x-auto text-slate-600 dark:text-slate-300">
              {output}
            </pre>
          )}
          {data && (
            <p className="mt-3 text-[10px] text-slate-400">
              单次调用超时 {data.timeout_seconds}s；批量调用上限 {data.max_calls_per_request} 次/请求
            </p>
          )}
        </div>

      </div>
    </div>
  )
}
