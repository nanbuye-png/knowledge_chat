export interface Document {
  id: string
  filename: string
  file_size: number
  file_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  chunk_count: number
  error_message?: string | null
  /** §5.2：文档级重试次数（0 = 一次成功/未重试） */
  retry_count?: number
  knowledge_base_id?: number | null
  created_at?: string
  updated_at?: string
}

export interface SourceReference {
  document_id: string
  filename: string
  chunk_index: number
  text: string
  /** §5.5：引用追溯（PDF 页号 / 章节标题；无法定位时为 null） */
  page?: number | null
  section?: string | null
}

export interface Citation {
  document_id: string
  filename: string
  chunk_id: number
  score: number
  page?: number | null
  section?: string | null
  /** 后端生成的展示串「文件名 · 第N页 · 章节」 */
  display?: string
  metadata?: Record<string, any>
}

export interface Message {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceReference[]
  citations?: Citation[]
  hasKnowledge?: boolean
  /** §5.6：拒答（检索无足够依据，属于正常业务结果，不是故障） */
  abstained?: boolean
  /** 拒答原因码：no_context / insufficient_context / low_retrieval_score / low_rerank_score */
  abstentionReason?: string | null
  /** 本次回答失败（限流/超时/内部错误），与拒答是两件事 */
  error?: string | null
  timestamp: number
}

export interface UploadResult {
  message: string
  document_id: string
  filename: string
  status: string
  /** §5.3 幂等：true = 该知识库内已存在相同内容，未新建记录、未派发任务 */
  skipped: boolean
  /** 被复用的既有文档 ID（skipped=true 时必有值） */
  duplicated_of?: string | null
}

/** 流式拒答控制帧（{"type":"no_result"}）的载荷。 */
export interface AbstentionInfo {
  abstained: boolean
  reason?: string | null
  message: string
  details?: Record<string, any>
}

/** 非流式 RAG 问答响应（POST /api/knowledge/query）。 */
export interface QueryAnswer {
  answer: string
  sources: SourceReference[]
  citations?: Citation[]
  has_knowledge: boolean
  abstained?: boolean
  abstention_reason?: string | null
  /** 非空表示本次回答失败（≠ 拒答），不能当成模型回答展示/统计 */
  error?: string | null
}

export interface ConversationMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ThemeState {
  theme: 'light' | 'dark'
  toggleTheme: () => void
}

export interface DocumentState {
  documents: Document[]
  loading: boolean
  fetchDocuments: (knowledgeBaseId: number) => Promise<void>
  addDocument: (doc: Document) => void
  removeDocument: (id: string) => void
  updateDocumentStatus: (id: string, status: Document['status'], chunk_count?: number) => void
}

export interface Conversation {
  id: number
  title: string
  knowledge_base_id?: number | null
  created_at: string
  updated_at: string
}

export interface UploadProgress {
  filename: string
  progress: number
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  error?: string
  /** §5.3 幂等命中：该知识库已有相同内容，未新建记录 */
  skipped?: boolean
  /** 后端返回的提示文案（如"已跳过重复处理"） */
  message?: string
}
