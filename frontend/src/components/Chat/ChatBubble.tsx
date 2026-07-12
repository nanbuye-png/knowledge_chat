import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { User, Bot, Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { Message } from '../../types'
import SourceReference from './SourceReference'
import CitationCard from './CitationCard'

interface ChatBubbleProps {
  message: Message
  isStreaming?: boolean
}

export default function ChatBubble({ message, isStreaming }: ChatBubbleProps) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} mb-4`}
    >
      {/* Avatar */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 200 }}
        className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center
                    shadow-sm ring-2 ring-white dark:ring-slate-800
                    ${isUser
                      ? 'bg-gradient-to-br from-primary-500 to-primary-600'
                      : 'bg-gradient-to-br from-slate-600 to-slate-700 dark:from-slate-500 dark:to-slate-600'
                    }`}
      >
        {isUser ? (
          <User className="w-5 h-5 text-white" />
        ) : (
          <Bot className="w-5 h-5 text-white" />
        )}
      </motion.div>

      {/* Message Content */}
      <div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Bubble */}
        <div
          className={`group relative px-4 py-3 rounded-2xl shadow-sm
            ${isUser
              ? 'bg-gradient-to-br from-primary-500 to-primary-600 text-white rounded-tr-md'
              : 'bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 rounded-tl-md border border-slate-200 dark:border-slate-700'
            }`}
        >
          {/* Content with Markdown */}
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
                          <div className="relative group/code my-3">
                            <div className="flex items-center justify-between px-4 py-1.5 bg-slate-800 rounded-t-lg text-xs text-slate-400">
                              <span>{match![1]}</span>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(codeStr)
                                }}
                                className="hover:text-white transition-colors"
                              >
                                复制
                              </button>
                            </div>
                            <SyntaxHighlighter
                              style={oneDark as any}
                              language={match![1]}
                              PreTag="div"
                              customStyle={{ margin: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0 }}
                            >
                              {codeStr}
                            </SyntaxHighlighter>
                          </div>
                        )
                      }
                      return (
                        <code className="bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-sm">
                          {children}
                        </code>
                      )
                    },
                    p: ({ children }) => <p className="leading-relaxed mb-2 last:mb-0">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-primary-300 pl-3 py-1 my-2 bg-slate-50 dark:bg-slate-800/50 rounded-r">
                        {children}
                      </blockquote>
                    ),
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

          {/* Copy button for assistant messages */}
          {!isUser && !isStreaming && (
            <button
              onClick={handleCopy}
              className="absolute -bottom-8 right-0 p-1.5 rounded-lg 
                         opacity-0 group-hover:opacity-100 transition-opacity duration-200
                         hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-green-500" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-slate-400" />
              )}
            </button>
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceReference sources={message.sources} />
        )}

        {!isUser && message.citations && message.citations.length > 0 && (
          <CitationCard citations={message.citations} />
        )}

        {/* No knowledge indicator */}
        {!isUser && message.hasKnowledge === false && !isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-2 text-xs text-slate-400 italic"
          >
            未在知识库中找到相关信息
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}