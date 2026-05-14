import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { useAuthStore } from '../auth-store'

const TOKEN_RESPONSE = {
  access_token: 'test-jwt-token',
  token_type: 'bearer',
  user_id: 'user-1',
  agency_id: 'agency-1',
}

beforeEach(() => {
  // the store reads its initial token from localStorage at module load — reset
  // both the store state and storage so each test starts clean
  useAuthStore.setState({ token: null, user: null, agency: null, isLoading: true })
  localStorage.clear()
})

describe('auth-store', () => {
  it('login stores the token and loads the user + agency', async () => {
    server.use(http.post(`${API}/auth/login`, () => HttpResponse.json(TOKEN_RESPONSE)))

    await useAuthStore.getState().login('owner@acme.example.com', 'pw')

    const s = useAuthStore.getState()
    expect(s.token).toBe('test-jwt-token')
    expect(localStorage.getItem('nuprop_token')).toBe('test-jwt-token')
    expect(s.user?.email).toBe('owner@acme.example.com')
    expect(s.agency?.name).toBe('Acme Agency')
  })

  it('register stores the token and loads the user + agency', async () => {
    server.use(http.post(`${API}/auth/register`, () => HttpResponse.json(TOKEN_RESPONSE)))

    await useAuthStore.getState().register('owner@acme.example.com', 'pw', 'Owner', 'Acme')

    expect(useAuthStore.getState().token).toBe('test-jwt-token')
    expect(localStorage.getItem('nuprop_token')).toBe('test-jwt-token')
  })

  it('logout clears the token and all user/agency state', () => {
    useAuthStore.setState({
      token: 'some-token',
      user: { id: 'u', email: 'e', full_name: 'n', agency_id: 'a', is_owner: true },
      agency: null,
    })
    localStorage.setItem('nuprop_token', 'some-token')

    useAuthStore.getState().logout()

    const s = useAuthStore.getState()
    expect(s.token).toBeNull()
    expect(s.user).toBeNull()
    expect(s.agency).toBeNull()
    expect(localStorage.getItem('nuprop_token')).toBeNull()
  })

  it('initialize without a stored token short-circuits without fetching', async () => {
    // MSW is set to error on unhandled requests — a stray fetch here would fail
    await useAuthStore.getState().initialize()
    const s = useAuthStore.getState()
    expect(s.isLoading).toBe(false)
    expect(s.user).toBeNull()
  })

  it('initialize with a valid token loads the user + agency', async () => {
    localStorage.setItem('nuprop_token', 'valid-token')
    await useAuthStore.getState().initialize()
    const s = useAuthStore.getState()
    expect(s.isLoading).toBe(false)
    expect(s.user?.email).toBe('owner@acme.example.com')
    expect(s.agency?.name).toBe('Acme Agency')
  })

  it('initialize with a token that fails to validate clears the token', async () => {
    localStorage.setItem('nuprop_token', 'stale-token')
    server.use(http.get(`${API}/auth/me`, () => new HttpResponse(null, { status: 500 })))

    await useAuthStore.getState().initialize()

    const s = useAuthStore.getState()
    expect(s.isLoading).toBe(false)
    expect(s.token).toBeNull()
    expect(localStorage.getItem('nuprop_token')).toBeNull()
  })
})
