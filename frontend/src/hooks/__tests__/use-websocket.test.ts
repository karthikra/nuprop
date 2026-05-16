import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useProposalWebSocket } from '../use-websocket'
import { useChatStore } from '../../stores/chat-store'

/** A minimal scriptable WebSocket stand-in. */
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  readyState = 0
  closed = false
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
  // test helpers
  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  useChatStore.getState().reset()
  localStorage.setItem('nuprop_token', 'test-token')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  localStorage.clear()
})

describe('useProposalWebSocket', () => {
  it('opens a WebSocket to the proposal channel with the auth token', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('/api/v1/chat/prop-1/ws')
    expect(MockWebSocket.instances[0].url).toContain('token=test-token')
  })

  it('does not connect without a proposalId', () => {
    renderHook(() => useProposalWebSocket(undefined))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('does not connect without a stored token', () => {
    localStorage.clear()
    renderHook(() => useProposalWebSocket('prop-1'))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('marks the store connected on open', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    expect(useChatStore.getState().isConnected).toBe(false)
    act(() => MockWebSocket.instances[0].open())
    expect(useChatStore.getState().isConnected).toBe(true)
  })

  it('dispatches a new_message event into the chat store', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    const message = {
      id: 'm1', proposal_id: 'prop-1', role: 'assistant', message_type: 'text',
      content: 'hi', extra_data: {}, phase: null, created_at: '2026-01-01T00:00:00Z',
    }
    act(() => MockWebSocket.instances[0].emit({ type: 'new_message', message }))
    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0].id).toBe('m1')
    expect(useChatStore.getState().isTyping).toBe(false)
  })

  it('dispatches a message_updated event by replacing the message in the store', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    const original = {
      id: 'm1', proposal_id: 'prop-1', role: 'assistant' as const, message_type: 'text',
      content: 'original', extra_data: {}, phase: null, created_at: '2026-01-01T00:00:00Z',
    }
    act(() => MockWebSocket.instances[0].emit({ type: 'new_message', message: original }))
    expect(useChatStore.getState().messages[0].content).toBe('original')

    const updated = { ...original, content: 'updated' }
    act(() => MockWebSocket.instances[0].emit({ type: 'message_updated', message: updated }))
    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0].content).toBe('updated')
  })

  it('dispatches a phase_change event into the chat store', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    act(() => MockWebSocket.instances[0].emit({ type: 'phase_change', phase: 'research' }))
    expect(useChatStore.getState().pipelinePhase).toBe('research')
  })

  it('dispatches typing and progress events', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    act(() => MockWebSocket.instances[0].emit({ type: 'typing', typing: true }))
    expect(useChatStore.getState().isTyping).toBe(true)

    act(() =>
      MockWebSocket.instances[0].emit({
        type: 'progress', agent: 'research', status: 'searching', detail: 'looking',
      }),
    )
    expect(useChatStore.getState().progress[0]).toEqual({
      agent: 'research', status: 'searching', detail: 'looking',
    })
  })

  it('routes ideation-channel new_message to ideationMessages, not messages', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    const message = {
      id: 'm-ideation-1', proposal_id: 'prop-1', role: 'system', message_type: 'text',
      content: "Couldn't reach Bedrock. Send another message to try again.",
      extra_data: { kind: 'error', error: 'bedrock unreachable' },
      phase: 'ideation', channel: 'ideation', created_at: '2026-01-01T00:00:00Z',
    }
    act(() => MockWebSocket.instances[0].emit({ type: 'new_message', message }))
    expect(useChatStore.getState().ideationMessages).toHaveLength(1)
    expect(useChatStore.getState().messages).toHaveLength(0)
    expect(useChatStore.getState().ideationMessages[0].id).toBe('m-ideation-1')
  })

  it('ignores malformed messages without throwing', () => {
    renderHook(() => useProposalWebSocket('prop-1'))
    expect(() => {
      act(() => MockWebSocket.instances[0].onmessage?.({ data: 'not json{' }))
    }).not.toThrow()
  })

  it('closes the socket and disables reconnect on unmount', () => {
    vi.useFakeTimers()
    const { unmount } = renderHook(() => useProposalWebSocket('prop-1'))
    const ws = MockWebSocket.instances[0]

    unmount()

    expect(ws.closed).toBe(true)
    expect(ws.onclose).toBeNull() // reconnect-on-close is intentionally disabled
    // even past the 3s reconnect window, no new socket is created
    vi.advanceTimersByTime(5000)
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
