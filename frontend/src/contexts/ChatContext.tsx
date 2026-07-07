import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChatState, Message, Conversation } from '../types'

type MessagesByMode = {
  knowledge: Message[]
  chat: Message[]
}

interface ChatStore extends ChatState {
  messagesByMode: MessagesByMode
  conversationList: Conversation[]
  currentConversationId: number | null
  setConversationList: (list: Conversation[]) => void
  setCurrentConversationId: (id: number | null) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      messagesByMode: {
        knowledge: [],
        chat: [],
      },
      messages: [],
      mode: 'knowledge',
      isStreaming: false,
      conversationList: [],
      currentConversationId: null,

      addMessage: (message: Message) =>
        set((state) => {
          const currentMode = state.mode
          const updatedMessagesByMode = {
            ...state.messagesByMode,
            [currentMode]: [...state.messagesByMode[currentMode], message],
          }
          return {
            messagesByMode: updatedMessagesByMode,
            messages: updatedMessagesByMode[currentMode],
          }
        }),

      updateLastMessage: (content: string) =>
        set((state) => {
          const currentMode = state.mode
          const modeMessages = [...state.messagesByMode[currentMode]]
          if (modeMessages.length > 0) {
            const last = { ...modeMessages[modeMessages.length - 1] }
            last.content = content
            modeMessages[modeMessages.length - 1] = last
          }
          return {
            messagesByMode: {
              ...state.messagesByMode,
              [currentMode]: modeMessages,
            },
            messages: modeMessages,
          }
        }),

      setMode: (mode: 'knowledge' | 'chat') =>
        set((state) => ({
          mode,
          messages: state.messagesByMode[mode] || [],
        })),

      setStreaming: (isStreaming: boolean) => set({ isStreaming }),

      clearMessages: () =>
        set((state) => ({
          messagesByMode: {
            ...state.messagesByMode,
            [state.mode]: [],
          },
          messages: [],
        })),

      setConversationList: (list: Conversation[]) => set({ conversationList: list }),

      setCurrentConversationId: (id: number | null) =>
        set({ currentConversationId: id }),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        messagesByMode: state.messagesByMode,
        mode: state.mode,
      }),
    }
  )
)
