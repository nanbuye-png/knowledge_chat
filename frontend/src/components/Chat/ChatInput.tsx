import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Send, Paperclip, X } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  onUpload: (file: File) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSend, onUpload, disabled, placeholder }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px'
    }
  }, [input])

  const handleSubmit = () => {
    if (!input.trim() || disabled) return
    onSend(input.trim())
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onUpload(file)
      e.target.value = ''
    }
  }

  return (
    <motion.div
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="relative"
    >
      <div className="flex items-end gap-2 bg-white dark:bg-slate-800/90 
                      rounded-2xl border border-slate-200 dark:border-slate-700
                      shadow-lg shadow-slate-200/50 dark:shadow-black/20
                      focus-within:ring-2 focus-within:ring-primary-500/30
                      focus-within:border-primary-500/50
                      transition-all duration-200">
        {/* Upload button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="flex-shrink-0 p-3 text-slate-400 hover:text-primary-500 
                     hover:bg-primary-50 dark:hover:bg-primary-900/30
                     rounded-xl transition-colors duration-200
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.md,.txt"
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Text input */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "输入你的问题... (Enter 发送, Shift+Enter 换行)"}
          rows={1}
          disabled={disabled}
          className="flex-1 py-3 bg-transparent text-slate-800 dark:text-slate-100
                     placeholder-slate-400 dark:placeholder-slate-500
                     resize-none outline-none text-sm leading-relaxed
                     disabled:opacity-50"
        />

        {/* Send button */}
        <motion.button
          onClick={handleSubmit}
          disabled={!input.trim() || disabled}
          className="flex-shrink-0 p-3 m-1 rounded-xl
                     bg-gradient-to-r from-primary-500 to-primary-600
                     text-white shadow-md shadow-primary-500/25
                     hover:shadow-lg hover:shadow-primary-500/30
                     disabled:opacity-40 disabled:cursor-not-allowed
                     transition-all duration-200"
          whileHover={input.trim() && !disabled ? { scale: 1.05 } : {}}
          whileTap={input.trim() && !disabled ? { scale: 0.95 } : {}}
        >
          <Send className="w-5 h-5" />
        </motion.button>
      </div>
    </motion.div>
  )
}