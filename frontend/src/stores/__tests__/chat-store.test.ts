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
    channel: 'main',
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

  it('updateMessage replaces a message in the messages list by id', () => {
    useChatStore.getState().addMessage(msg('m1', { content: 'orig' }))
    useChatStore.getState().updateMessage(msg('m1', { content: 'updated' }))
    expect(useChatStore.getState().messages[0].content).toBe('updated')
  })

  it('updateMessage is a no-op when the message id is not present', () => {
    useChatStore.getState().addMessage(msg('m1', { content: 'orig' }))
    useChatStore.getState().updateMessage(msg('m999', { content: 'ghost' }))
    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0].content).toBe('orig')
  })
})

describe('chat-store channel routing', () => {
  beforeEach(() => useChatStore.getState().reset())

  function mainMsg(id: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
    return msg(id, { channel: 'main', ...overrides })
  }

  function ideationMsg(id: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
    return msg(id, { channel: 'ideation', ...overrides })
  }

  it('addMessage with channel=main lands in messages, not ideationMessages', () => {
    useChatStore.getState().addMessage(msg('m1', { channel: 'main' }))
    expect(useChatStore.getState().messages.map(m => m.id)).toEqual(['m1'])
    expect(useChatStore.getState().ideationMessages).toEqual([])
  })

  it('addMessage with channel=ideation lands in ideationMessages, not messages', () => {
    useChatStore.getState().addMessage(msg('i1', { channel: 'ideation' }))
    expect(useChatStore.getState().ideationMessages.map(m => m.id)).toEqual(['i1'])
    expect(useChatStore.getState().messages).toEqual([])
  })

  it('dedupes by id within each channel independently', () => {
    useChatStore.getState().addMessage(msg('m1', { channel: 'main' }))
    useChatStore.getState().addMessage(msg('m1', { channel: 'main' }))
    useChatStore.getState().addMessage(msg('m1', { channel: 'ideation' }))
    expect(useChatStore.getState().messages.length).toBe(1)
    expect(useChatStore.getState().ideationMessages.length).toBe(1)
  })

  it('updateMessage routes by channel — ideation msg updates ideationMessages, not messages', () => {
    useChatStore.getState().addMessage(ideationMsg('i1'))
    const updated = { ...ideationMsg('i1'), content: 'updated' }
    useChatStore.getState().updateMessage(updated)
    expect(useChatStore.getState().ideationMessages[0].content).toBe('updated')
    expect(useChatStore.getState().messages).toEqual([])
  })

  it('updateMessage on a main-channel message still updates messages', () => {
    useChatStore.getState().addMessage(mainMsg('m1'))
    const updated = { ...mainMsg('m1'), content: 'updated main' }
    useChatStore.getState().updateMessage(updated)
    expect(useChatStore.getState().messages[0].content).toBe('updated main')
    expect(useChatStore.getState().ideationMessages).toEqual([])
  })
})

describe('chat-store mergeIdeationMessages', () => {
  beforeEach(() => useChatStore.getState().reset())

  function ideationMsg(id: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
    return msg(id, { channel: 'ideation', ...overrides })
  }

  it('adds all messages on an empty slice and preserves order', () => {
    const batch = [ideationMsg('i1'), ideationMsg('i2'), ideationMsg('i3')]
    useChatStore.getState().mergeIdeationMessages(batch)
    expect(useChatStore.getState().ideationMessages.map((m) => m.id)).toEqual(['i1', 'i2', 'i3'])
  })

  it('dedupes against existing ids — only the new messages are appended', () => {
    useChatStore.getState().mergeIdeationMessages([ideationMsg('i1'), ideationMsg('i2')])
    useChatStore.getState().mergeIdeationMessages([
      ideationMsg('i1'), // already there
      ideationMsg('i2'), // already there
      ideationMsg('i3'), // new
    ])
    expect(useChatStore.getState().ideationMessages.map((m) => m.id)).toEqual(['i1', 'i2', 'i3'])
  })

  it('is a no-op when called with an empty array (no state churn)', () => {
    useChatStore.getState().mergeIdeationMessages([ideationMsg('i1')])
    const before = useChatStore.getState().ideationMessages
    useChatStore.getState().mergeIdeationMessages([])
    expect(useChatStore.getState().ideationMessages).toBe(before)
  })

  it('does not touch the main channel even with channel=main inputs', () => {
    useChatStore.getState().mergeIdeationMessages([
      msg('x1', { channel: 'main' }),
      ideationMsg('i1'),
    ])
    expect(useChatStore.getState().messages).toEqual([])
    expect(useChatStore.getState().ideationMessages.map((m) => m.id)).toEqual(['x1', 'i1'])
  })
})

describe('chat-store isIdeationTyping', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('setIdeationTyping toggles the flag independently of isTyping', () => {
    expect(useChatStore.getState().isIdeationTyping).toBe(false)
    useChatStore.getState().setIdeationTyping(true)
    expect(useChatStore.getState().isIdeationTyping).toBe(true)
    expect(useChatStore.getState().isTyping).toBe(false)
    useChatStore.getState().setIdeationTyping(false)
    expect(useChatStore.getState().isIdeationTyping).toBe(false)
  })

  it('reset clears isIdeationTyping along with isTyping', () => {
    useChatStore.getState().setTyping(true)
    useChatStore.getState().setIdeationTyping(true)
    useChatStore.getState().reset()
    expect(useChatStore.getState().isTyping).toBe(false)
    expect(useChatStore.getState().isIdeationTyping).toBe(false)
  })
})
