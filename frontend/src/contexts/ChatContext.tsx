import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, Conversation } from '../types'

interface ChatStore {
  messages: Message[]
  isStreaming: boolean
  conversationList: Conversation[]
  currentConversationId: number | null

  addMessage: (message: Message) => void
  updateLastMessage: (content: string) => void
  setStreaming: (streaming: boolean) => void
  clearMessages: () => void
  setConversationList: (list: Conversation[]) => void
  setCurrentConversationId: (id: number | null) => void
  loadMessages: (messages: Message[]) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      messages: [],
      isStreaming: false,
      conversationList: [],
      currentConversationId: null,

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

      clearMessages: () => set({ messages: [] }),

      setConversationList: (list: Conversation[]) => set({ conversationList: list }),

      setCurrentConversationId: (id: number | null) =>
        set({ currentConversationId: id }),

      loadMessages: (messages: Message[]) => set({ messages }),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        messages: state.messages,
        conversationList: state.conversationList,
        currentConversationId: state.currentConversationId,
      }),
    }
  )
)