import { useState } from 'react'
import { motion } from 'framer-motion'
import { User, Bot, Copy, Check, RefreshCw, AlertCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { Message } from '../../types'
import CitationCard from './CitationCard'

interface Props {
  message: Message
  isStreaming?: boolean
  onRetry?: () => void
}

export default function ChatMessage({ message, isStreaming, onRetry }: Props) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const isError = message.content.startsWith('抱歉，')

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`flex items-start gap-3 mb-5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center shadow-sm
        ring-2 ring-white dark:ring-slate-800
        ${isUser
          ? 'bg-gradient-to-br from-primary-500 to-primary-600'
          : 'bg-gradient-to-br from-slate-600 to-slate-700 dark:from-slate-500 dark:to-slate-600'
        }`}
      >
        {isUser ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
      </div>

      <div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Label */}
        <span className={`text-xs font-medium mb-1 px-2 py-0.5 rounded-full
          ${isUser
            ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
            : 'text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800'
          }`}
        >
          {isUser ? 'You' : 'Assistant'}
        </span>

        {/* Bubble */}
        <div className={`relative group px-4 py-3 rounded-2xl shadow-sm w-full
          ${isUser
            ? 'bg-gradient-to-br from-primary-500 to-primary-600 text-white rounded-tr-md'
            : isError
              ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-tl-md border border-red-200 dark:border-red-800'
              : 'bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 rounded-tl-md border border-slate-200 dark:border-slate-700'
          }`}
        >
          {/* Content */}
          <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : 'dark:prose-invert'}`}>
            {isUser ? (
              <p className="whitespace-pre-wrap">{message.content}</p>
            ) : (
              <div className="markdown-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    code({ className, children }) {
                      const match = /language-(\w+)/.exec(className || '')
                      const codeStr = String(children).replace(/\n$/, '')
                      const isInline = !match
                      if (!isInline) {
                        return (
                          <div className="relative group/code my-3 rounded-lg overflow-hidden border border-slate-700">
                            <div className="flex items-center justify-between px-4 py-1.5 bg-slate-800 text-xs text-slate-400">
                              <span>{match![1]}</span>
                              <button onClick={() => navigator.clipboard.writeText(codeStr)}
                                className="hover:text-white transition-colors">复制</button>
                            </div>
                            <SyntaxHighlighter
                              style={oneDark as any}
                              language={match![1]}
                              PreTag="div"
                              customStyle={{ margin: 0, borderRadius: 0 }}
                            >
                              {codeStr}
                            </SyntaxHighlighter>
                          </div>
                        )
                      }
                      return <code className="bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-sm">{children}</code>
                    },
                    table({ children }) {
                      return (
                        <div className="overflow-x-auto my-3">
                          <table className="min-w-full text-sm border-collapse border border-slate-300 dark:border-slate-600">
                            {children}
                          </table>
                        </div>
                      )
                    },
                    th({ children }) {
                      return <th className="border border-slate-300 dark:border-slate-600 px-3 py-2 bg-slate-50 dark:bg-slate-700 font-medium">{children}</th>
                    },
                    td({ children }) {
                      return <td className="border border-slate-300 dark:border-slate-600 px-3 py-2">{children}</td>
                    },
                    p: ({ children }) => <p className="leading-relaxed mb-2 last:mb-0">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-primary-300 pl-3 py-1 my-2 bg-slate-50 dark:bg-slate-800/50 rounded-r">{children}</blockquote>
                    ),
                    h1: ({ children }) => <h1 className="text-lg font-bold mt-4 mb-2">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-base font-bold mt-3 mb-2">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-sm font-bold mt-2 mb-1">{children}</h3>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </div>

          {/* Streaming cursor */}
          {isStreaming && (
            <span className="inline-block w-2 h-4 bg-primary-500 dark:bg-primary-400 animate-blink ml-0.5" />
          )}

          {/* Actions */}
          {!isUser && !isStreaming && message.content && (
            <div className="flex items-center gap-1 mt-2 pt-2 border-t border-slate-200/50 dark:border-slate-700/50">
              <button onClick={handleCopy}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
                {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              {onRetry && (
                <button onClick={onRetry}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-slate-400 hover:text-primary-500 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
                  <RefreshCw className="w-3 h-3" />
                  Retry
                </button>
              )}
            </div>
          )}
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <CitationCard citations={message.citations} />
        )}

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2">
            <CitationCard citations={message.sources.map(s => ({
              document_id: s.document_id,
              filename: s.filename,
              chunk_id: s.chunk_index,
              score: 0,
            }))} />
          </div>
        )}

        {/* No knowledge indicator */}
        {!isUser && message.hasKnowledge === false && !isStreaming && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="mt-2 flex items-center gap-1 text-xs text-amber-500">
            <AlertCircle className="w-3 h-3" />
            未在知识库中找到相关信息
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}