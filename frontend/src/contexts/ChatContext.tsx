import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChatState, Message } from '../types'

type MessagesByMode = {
  knowledge: Message[]
  chat: Message[]
}

interface ChatStore extends ChatState {
  messagesByMode: MessagesByMode
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
