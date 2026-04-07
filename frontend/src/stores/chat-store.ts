import { create } from 'zustand'
import type { ChatMessage, ProgressItem } from '../types/proposal'

interface ChatState {
  messages: ChatMessage[]
  pipelinePhase: string
  isConnected: boolean
  isSending: boolean
  isTyping: boolean
  progress: ProgressItem[]

  setMessages: (msgs: ChatMessage[]) => void
  addMessage: (msg: ChatMessage) => void
  setPipelinePhase: (phase: string) => void
  setConnected: (connected: boolean) => void
  setSending: (sending: boolean) => void
  setTyping: (typing: boolean) => void
  updateProgress: (item: ProgressItem) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  pipelinePhase: 'brief',
  isConnected: false,
  isSending: false,
  isTyping: false,
  progress: [],

  setMessages: (msgs) => set({ messages: msgs }),

  addMessage: (msg) =>
    set((state) => {
      if (state.messages.some((m) => m.id === msg.id)) return state
      return { messages: [...state.messages, msg] }
    }),

  setPipelinePhase: (phase) => set({ pipelinePhase: phase }),
  setConnected: (connected) => set({ isConnected: connected }),
  setSending: (sending) => set({ isSending: sending }),
  setTyping: (typing) => set({ isTyping: typing }),

  updateProgress: (item) =>
    set((state) => {
      const existing = state.progress.findIndex((p) => p.agent === item.agent)
      if (existing >= 0) {
        const updated = [...state.progress]
        updated[existing] = item
        return { progress: updated }
      }
      return { progress: [...state.progress, item] }
    }),

  reset: () => set({
    messages: [], pipelinePhase: 'brief', isConnected: false,
    isSending: false, isTyping: false, progress: [],
  }),
}))
