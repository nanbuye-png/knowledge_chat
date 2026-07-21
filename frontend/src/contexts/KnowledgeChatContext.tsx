import { create } from 'zustand'
import type { Message, SourceReference, Conversation } from '../types'

interface KnowledgeChatStore {
  messages: Message[]
  isStreaming: boolean
  conversationList: Conversation[]
  currentConversationId: number | null
  currentSources: SourceReference[]

  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setStreaming: (streaming: boolean) => void
  clearMessages: () => void
  setConversationList: (list: Conversation[]) => void
  setCurrentConversationId: (id: number | null) => void
  loadMessages: (messages: Message[]) => void
  setSources: (sources: SourceReference[]) => void
}

export const useKnowledgeChatStore = create<KnowledgeChatStore>()(
  (set) => ({
    messages: [],
    isStreaming: false,
    conversationList: [],
    currentConversationId: null,
    currentSources: [],

    addMessage: (message: Message) =>
      set((state) => ({
        messages: [...state.messages, message],
      })),

    updateLastMessage: (content: string) =>
      set((state) => {
        const msgs = [...state.messages]
        if (msgs.length > 0) {
          const last = { ...msgs[msgs.length - 1] }
          last.content = content
          msgs[msgs.length - 1] = last
        }
        return { messages: msgs }
      }),

    setStreaming: (isStreaming: boolean) => set({ isStreaming }),

    clearMessages: () => set({ messages: [], currentSources: [] }),

    setConversationList: (list: Conversation[]) => set({ conversationList: list }),

    setCurrentConversationId: (id: number | null) =>
      set({ currentConversationId: id }),

    loadMessages: (messages: Message[]) => set({ messages }),

    setSources: (sources: SourceReference[]) => set({ currentSources: sources }),
  })
)