export interface Document {
  id: string
  filename: string
  file_size: number
  file_type: string
  status: 'processing' | 'completed' | 'failed'
  chunk_count: number
  error_message?: string | null
  knowledge_base_id?: number | null
  created_at?: string
  updated_at?: string
}

export interface SourceReference {
  document_id: string
  filename: string
  chunk_index: number
  text: string
}

export interface Citation {
  document_id: string
  filename: string
  chunk_id: number
  score: number
  metadata?: Record<string, any>
}

export interface Message {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceReference[]
  citations?: Citation[]
  hasKnowledge?: boolean
  timestamp: number
}

export interface ConversationMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatState {
  messages: Message[]
  mode: 'knowledge' | 'chat'
  isStreaming: boolean
  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setMode: (mode: 'knowledge' | 'chat') => void
  setStreaming: (streaming: boolean) => void
  clearMessages: () => void
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
  created_at: string
  updated_at: string
}

export interface UploadProgress {
  filename: string
  progress: number
  status: 'uploading' | 'processing' | 'completed' | 'failed'
  error?: string
}
