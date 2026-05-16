import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { api, formatApiError } from '../client'

beforeEach(() => localStorage.clear())

describe('api client interceptors', () => {
  it('does not attach an Authorization header when no token is stored', async () => {
    let received: string | null = 'unset'
    server.use(
      http.get(`${API}/ping`, ({ request }) => {
        received = request.headers.get('authorization')
        return HttpResponse.json({ ok: true })
      }),
    )
    await api.get('/ping')
    expect(received).toBeNull()
  })

  it('injects the bearer token from localStorage on each request', async () => {
    localStorage.setItem('nuprop_token', 'abc-123')
    let received: string | null = null
    server.use(
      http.get(`${API}/ping`, ({ request }) => {
        received = request.headers.get('authorization')
        return HttpResponse.json({ ok: true })
      }),
    )
    await api.get('/ping')
    expect(received).toBe('Bearer abc-123')
  })

  it('clears the stored token on a 401 response', async () => {
    localStorage.setItem('nuprop_token', 'expired-token')
    server.use(
      http.get(`${API}/protected`, () => new HttpResponse(null, { status: 401 })),
    )
    await expect(api.get('/protected')).rejects.toBeDefined()
    expect(localStorage.getItem('nuprop_token')).toBeNull()
  })
})

describe('formatApiError', () => {
  it('returns the string detail unchanged (HTTPException shape)', () => {
    const err = { response: { data: { detail: 'Invalid credentials' } } }
    expect(formatApiError(err, 'fallback')).toBe('Invalid credentials')
  })

  it('joins msg fields from a Pydantic 422 array detail', () => {
    const err = {
      response: {
        data: {
          detail: [
            { type: 'value_error', loc: ['body', 'email'], msg: 'not a valid email', input: 'x@y.local', ctx: {} },
            { type: 'missing', loc: ['body', 'full_name'], msg: 'Field required', input: {} },
          ],
        },
      },
    }
    expect(formatApiError(err, 'fallback')).toBe('not a valid email; Field required')
  })

  it('falls back when detail is missing', () => {
    expect(formatApiError({}, 'fallback')).toBe('fallback')
    expect(formatApiError(undefined, 'fallback')).toBe('fallback')
    expect(formatApiError(null, 'fallback')).toBe('fallback')
  })

  it('falls back when detail array has no msg fields', () => {
    const err = { response: { data: { detail: [{ type: 'value_error' }, 'unstructured'] } } }
    expect(formatApiError(err, 'fallback')).toBe('fallback')
  })

  it('always returns a string (never an object) — guards React error #31', () => {
    const arrayErr = { response: { data: { detail: [{ type: 'x', loc: [], msg: 'oops', input: {}, ctx: {} }] } } }
    const objectErr = { response: { data: { detail: { unexpected: 'shape' } } } }
    expect(typeof formatApiError(arrayErr, 'fallback')).toBe('string')
    expect(typeof formatApiError(objectErr, 'fallback')).toBe('string')
  })
})
