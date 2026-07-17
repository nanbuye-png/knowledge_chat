import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Cpu, Database, FileText, Gauge, Save, RefreshCw } from 'lucide-react'
import * as adminApi from '../../api/admin'

interface ConfigSection {
  title: string
  icon: React.ElementType
  fields: { key: string; label: string; type: string; value: string }[]
}

function SystemConfig() {
  const [sections, setSections] = useState<ConfigSection[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const fetchConfig = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminApi.getSystemConfig()
      const configSections: ConfigSection[] = [
        {
          title: 'LLM Provider', icon: Cpu,
          fields: [
            { key: 'llm_provider', label: 'Provider', type: 'text', value: data.llm_provider || 'deepseek' },
            { key: 'llm_model', label: 'Model', type: 'text', value: data.llm_model || 'deepseek-chat' },
          ],
        },
        {
          title: 'Embedding', icon: Database,
          fields: [
            { key: 'embedding_model', label: 'Embedding Model', type: 'text', value: data.embedding_model || 'BAAI/bge-small-zh-v1.5' },
            { key: 'embedding_dim', label: 'Dimension', type: 'number', value: String(data.embedding_dim || 768) },
          ],
        },
        {
          title: 'Document Processing', icon: FileText,
          fields: [
            { key: 'chunk_size', label: 'Chunk Size', type: 'number', value: String(data.chunk_size || 2000) },
            { key: 'chunk_overlap', label: 'Chunk Overlap', type: 'number', value: String(data.chunk_overlap || 200) },
          ],
        },
        {
          title: 'Rate Limit', icon: Gauge,
          fields: [
            { key: 'rate_limit_window', label: 'Window (seconds)', type: 'number', value: String(data.rate_limit_window || 60) },
            { key: 'rate_limit_chat', label: 'Chat Limit', type: 'number', value: String(data.rate_limit_chat || 20) },
            { key: 'rate_limit_upload', label: 'Upload Limit', type: 'number', value: String(data.rate_limit_upload || 10) },
          ],
        },
      ]
      setSections(configSections)
    } catch { setMsg('加载配置失败') } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  const updateField = (si: number, fi: number, value: string) => {
    setSections(prev => {
      const updated = [...prev]
      updated[si] = { ...updated[si], fields: [...updated[si].fields] }
      updated[si].fields[fi] = { ...updated[si].fields[fi], value }
      return updated
    })
  }

  const handleSave = async () => {
    setSaving(true); setMsg(null)
    try {
      const config: Record<string, any> = {}
      sections.forEach(s => s.fields.forEach(f => { config[f.key] = f.value }))
      await adminApi.updateSystemConfig(config)
      setMsg('配置已保存')
      setTimeout(() => setMsg(null), 3000)
    } catch (err: any) {
      setMsg('保存失败: ' + (err.message || '未知错误'))
    } finally { setSaving(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" /></div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">系统配置</h1>
          <p className="text-sm text-slate-500 mt-1">管理 LLM、嵌入模型、文档处理和速率限制配置</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchConfig} className="p-2 rounded-lg text-slate-400 hover:text-primary-500 hover:bg-slate-100">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 text-sm">
            <Save className="w-4 h-4" />{saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
      {msg && (
        <div className={`mb-4 p-3 rounded-xl text-sm ${msg.includes('失败') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>{msg}</div>
      )}
      <div className="space-y-4">
        {sections.map((section, si) => (
          <motion.div key={section.title} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: si * 0.05 }}
            className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center gap-2">
              <section.icon className="w-4 h-4 text-primary-500" />
              <h2 className="font-semibold text-sm text-slate-700 dark:text-slate-200">{section.title}</h2>
            </div>
            <div className="p-5 space-y-4">
              {section.fields.map((field, fi) => (
                <div key={field.key}>
                  <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{field.label}</label>
                  <input type={field.type} value={field.value}
                    onChange={(e) => updateField(si, fi, e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 outline-none focus:ring-2 focus:ring-primary-500/30" />
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

export default SystemConfig
