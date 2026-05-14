import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '../chat-store'
import type { ChatMessage } from '../../types/proposal'

function msg(id: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id,
    proposal_id: 'p1',
    role: 'assistant',
    message_type: 'text',
    content: 'hello',
    extra_data: {},
    phase: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('chat-store', () => {
  beforeEach(() => {
    useChatStore.getState().reset()
  })

  it('addMessage appends a new message', () => {
    useChatStore.getState().addMessage(msg('m1'))
    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(['m1'])
  })

  it('addMessage dedupes by id and keeps the first copy', () => {
    const { addMessage } = useChatStore.getState()
    addMessage(msg('m1'))
    addMessage(msg('m1', { content: 'duplicate' }))
    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0].content).toBe('hello')
  })

  it('setMessages replaces the whole list', () => {
    useChatStore.getState().setMessages([msg('a'), msg('b')])
    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(['a', 'b'])
  })

  it('updateProgress appends a new agent', () => {
    useChatStore.getState().updateProgress({ agent: 'research', status: 'searching', detail: 'looking' })
    expect(useChatStore.getState().progress).toHaveLength(1)
  })

  it('updateProgress upserts an existing agent in place', () => {
    const { updateProgress } = useChatStore.getState()
    updateProgress({ agent: 'research', status: 'searching', detail: 'looking' })
    updateProgress({ agent: 'benchmarks', status: 'searching', detail: 'pricing' })
    updateProgress({ agent: 'research', status: 'complete', detail: 'done' })
    const progress = useChatStore.getState().progress
    expect(progress).toHaveLength(2)
    expect(progress[0]).toEqual({ agent: 'research', status: 'complete', detail: 'done' })
    expect(progress[1].agent).toBe('benchmarks')
  })

  it('phase and flag setters update state', () => {
    const s = useChatStore.getState()
    s.setPipelinePhase('research')
    s.setConnected(true)
    s.setSending(true)
    s.setTyping(true)
    const next = useChatStore.getState()
    expect(next.pipelinePhase).toBe('research')
    expect(next.isConnected).toBe(true)
    expect(next.isSending).toBe(true)
    expect(next.isTyping).toBe(true)
  })

  it('reset returns the store to its defaults', () => {
    const s = useChatStore.getState()
    s.addMessage(msg('m1'))
    s.setPipelinePhase('complete')
    s.setConnected(true)
    s.updateProgress({ agent: 'research', status: 'complete', detail: 'done' })
    s.reset()
    const next = useChatStore.getState()
    expect(next.messages).toEqual([])
    expect(next.pipelinePhase).toBe('brief')
    expect(next.isConnected).toBe(false)
    expect(next.progress).toEqual([])
  })
})
