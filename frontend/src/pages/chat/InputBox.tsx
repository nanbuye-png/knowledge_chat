import { useState, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Send, Paperclip, StopCircle, Sparkles } from 'lucide-react'

interface Props {
  onSend: (content: string) => void
  onUpload?: (file: File) => void
  disabled?: boolean
  mode: 'knowledge' | 'chat'
  placeholder?: string
}

export default function InputBox({ onSend, onUpload, disabled, mode, placeholder }: Props) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    }
  }, [input])

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setInput('')
  }, [input, disabled, onSend])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && onUpload) {
      onUpload(file)
    }
    e.target.value = ''
  }, [onUpload])

  const placeholderText = placeholder || (mode === 'knowledge'
    ? '输入你的问题，AI将基于知识库回答...'
    : '随便聊聊吧...')

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative"
    >
      <div className="flex items-end gap-2 bg-white dark:bg-slate-800/80 
                      border border-slate-200 dark:border-slate-700 
                      rounded-2xl shadow-sm hover:shadow-md 
                      transition-shadow duration-200
                      focus-within:ring-2 focus-within:ring-primary-500/30 
                      focus-within:border-primary-500/50
                      px-4 py-3">
        {/* Upload button */}
        {onUpload && mode === 'knowledge' && (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="flex-shrink-0 p-1.5 rounded-lg text-slate-400 
                         hover:text-primary-500 hover:bg-primary-50 
                         dark:hover:bg-primary-900/20 transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed"
              title="上传文档"
            >
              <Paperclip className="w-4 h-4" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc,.md,.txt"
              className="hidden"
              onChange={handleFileChange}
            />
          </>
        )}

        {/* Textarea */}
        <div className="flex-1 min-w-0">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholderText}
            rows={1}
            disabled={disabled}
            className="w-full resize-none bg-transparent text-sm
                       text-slate-800 dark:text-slate-100
                       placeholder-slate-400 dark:placeholder-slate-500
                       outline-none scrollbar-thin
                       disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ maxHeight: '200px' }}
          />
        </div>

        {/* Mode indicator */}
        <div className="flex-shrink-0 flex items-center gap-1">
          {mode === 'knowledge' ? (
            <Sparkles className="w-3.5 h-3.5 text-primary-400" />
          ) : (
            <Sparkles className="w-3.5 h-3.5 text-slate-400" />
          )}

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={disabled || !input.trim()}
            className="flex-shrink-0 p-2 rounded-xl
                       bg-gradient-to-r from-primary-500 to-primary-600
                       text-white shadow-sm shadow-primary-500/25
                       hover:shadow-md hover:shadow-primary-500/30
                       hover:from-primary-600 hover:to-primary-700
                       transition-all duration-200 active:scale-95
                       disabled:opacity-40 disabled:cursor-not-allowed
                       disabled:hover:shadow-none disabled:active:scale-100"
          >
            {disabled ? (
              <StopCircle className="w-4 h-4" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Hint text */}
      {mode === 'knowledge' && (
        <p className="text-[10px] text-slate-400 text-center mt-1.5">
          AI 回复基于已上传的知识库内容，请确保相关信息已上传
        </p>
      )}
    </motion.div>
  )
}