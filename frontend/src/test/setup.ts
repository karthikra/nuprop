import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { act, cleanup, configure } from '@testing-library/react'
import { server } from './mocks/server'

// ── Fake-timer / React 19 compatibility ─────────────────────────────────────
//
// Problem: @testing-library/react v16's asyncWrapper creates a setTimeout(0)
// to drain microtasks after each user-event API call, then advances it only
// when Jest fake timers are detected (via `jestFakeTimersAreEnabled`, which
// checks `typeof jest`).  Vitest v4 doesn't expose `globalThis.jest`, so that
// branch never fires and the await hangs indefinitely when fake timers are
// active via vi.useFakeTimers().
//
// Second problem: React 19 concurrent mode schedules state updates through
// its Scheduler, which uses MessageChannel in jsdom/Node.  MessageChannel
// messages are macrotasks — they don't run until the JS stack is clear and an
// awaiting Promise yield occurs.  This means `vi.advanceTimersByTime(N)` can
// fire a component's setTimeout callback (calling setState), but the resulting
// React re-render is still pending in the MessageChannel queue when the next
// synchronous `expect()` runs.
//
// Fixes:
//  1. Replace asyncWrapper so it (a) handles vitest fake timers, and (b)
//     yields a real macrotask (using the pre-fake setTimeout) so the React
//     scheduler's MessageChannel message can flush between user-event calls.
//  2. Patch vi.advanceTimersByTime to wrap execution in React.act() so that
//     any React state updates triggered by the fired timers are committed to
//     the DOM before control returns to the test.

// Capture the real (unfaked) setTimeout BEFORE any test installs fake timers.
const realSetTimeout = globalThis.setTimeout.bind(globalThis)

configure({
  asyncWrapper: async (cb) => {
    // Mirror the IS_REACT_ACT_ENVIRONMENT toggle from the default wrapper so
    // React doesn't emit out-of-act warnings during each user-event call.
    const prev = (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = false
    try {
      const result = await cb()
      // Advance fake timers by 0 so any 0-ms timeouts user-event registered
      // (e.g. its internal delay) fire immediately.
      if (vi.isFakeTimers()) vi.advanceTimersByTime(0)
      // Yield a genuine macrotask via the real setTimeout so any pending
      // MessageChannel messages (React 19 scheduler) get to run before we
      // restore the act-environment flag and return.
      await new Promise<void>(resolve => realSetTimeout(resolve, 0))
      return result
    } finally {
      ;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = prev
    }
  },
})

// Patch vi.advanceTimersByTime so that when fake timers are active, timer
// callbacks that call React setState() are committed to the DOM synchronously
// (by running inside React.act()).  Without this, the state update is enqueued
// in the React scheduler but doesn't flush before the next synchronous
// assertion runs.
const _origAdvance = vi.advanceTimersByTime.bind(vi)
vi.advanceTimersByTime = (ms: number) => {
  if (vi.isFakeTimers()) {
    act(() => { _origAdvance(ms) })
  } else {
    _origAdvance(ms)
  }
}

// ── MSW lifecycle ────────────────────────────────────────────────────────────
// `error` on unhandled requests keeps tests honest — every network call a
// component makes must be explicitly mocked.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
  // Restore real timers if any test activated fake timers via vi.useFakeTimers()
  // and the finally-block restoration was skipped (e.g. due to a timeout).
  vi.useRealTimers()
})

afterAll(() => server.close())

// ── jsdom gaps ───────────────────────────────────────────────────────────────
// jsdom has no layout engine — components that read scrollHeight get 0, which
// is harmless. matchMedia is not implemented at all; stub it defensively.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}
