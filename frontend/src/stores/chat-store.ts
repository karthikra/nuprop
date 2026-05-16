import { create } from 'zustand'
import type { ChatMessage, ProgressItem } from '../types/proposal'

interface ChatState {
  messages: ChatMessage[]
  ideationMessages: ChatMessage[]
  pipelinePhase: string
  isConnected: boolean
  isSending: boolean
  isTyping: boolean
  progress: ProgressItem[]

  setMessages: (msgs: ChatMessage[]) => void
  addMessage: (msg: ChatMessage) => void
  updateMessage: (msg: ChatMessage) => void
  mergeIdeationMessages: (msgs: ChatMessage[]) => void
  setPipelinePhase: (phase: string) => void
  setConnected: (connected: boolean) => void
  setSending: (sending: boolean) => void
  setTyping: (typing: boolean) => void
  updateProgress: (item: ProgressItem) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  ideationMessages: [],
  pipelinePhase: 'brief',
  isConnected: false,
  isSending: false,
  isTyping: false,
  progress: [],

  setMessages: (msgs) => set({ messages: msgs }),

  addMessage: (msg) =>
    set((state) => {
      const target = msg.channel === 'ideation' ? 'ideationMessages' : 'messages'
      const existing = state[target as keyof ChatState] as ChatMessage[]
      if (existing.some((m) => m.id === msg.id)) return {}
      return { [target]: [...existing, msg] } as Partial<ChatState>
    }),

  updateMessage: (msg) =>
    set((state) => {
      const target = msg.channel === 'ideation' ? 'ideationMessages' : 'messages'
      const arr = state[target] as ChatMessage[]
      const idx = arr.findIndex((m) => m.id === msg.id)
      if (idx < 0) return {}
      const next = [...arr]
      next[idx] = msg
      return { [target]: next } as Partial<ChatState>
    }),

  // Merge a batch of server-fetched ideation messages into the slice in a single
  // O(n) pass — used by IdeationDrawer's hydration on every TanStack refetch.
  // Avoids the O(n²) cost of calling addMessage per message (which does its own
  // .some() scan each time).
  mergeIdeationMessages: (msgs) =>
    set((state) => {
      if (!msgs.length) return {}
      const existing = new Set(state.ideationMessages.map((m) => m.id))
      const toAdd = msgs.filter((m) => !existing.has(m.id))
      if (!toAdd.length) return {}
      return { ideationMessages: [...state.ideationMessages, ...toAdd] }
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
    messages: [], ideationMessages: [], pipelinePhase: 'brief', isConnected: false,
    isSending: false, isTyping: false, progress: [],
  }),
}))
