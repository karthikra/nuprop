import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './mocks/server'

// ── MSW lifecycle ────────────────────────────────────────────────────────────
// `error` on unhandled requests keeps tests honest — every network call a
// component makes must be explicitly mocked.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
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
