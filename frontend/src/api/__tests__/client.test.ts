import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { api } from '../client'

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
