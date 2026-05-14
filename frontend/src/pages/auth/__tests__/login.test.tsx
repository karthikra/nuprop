import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { useAuthStore } from '../../../stores/auth-store'
import { LoginPage } from '../login'

beforeEach(() => {
  useAuthStore.setState({ token: null, user: null, agency: null, isLoading: false })
  localStorage.clear()
})

describe('LoginPage', () => {
  it('logs in and stores the token on valid credentials', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json({
          access_token: 'jwt-abc', token_type: 'bearer', user_id: 'u1', agency_id: 'a1',
        }),
      ),
    )
    const { container } = renderWithProviders(<LoginPage />)

    await user.type(screen.getByRole('textbox'), 'owner@acme.example.com')
    await user.type(container.querySelector('input[type="password"]')!, 'pw123456')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(localStorage.getItem('nuprop_token')).toBe('jwt-abc'))
  })

  it('shows an error message on invalid credentials', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/auth/login`, () => new HttpResponse(null, { status: 401 })),
    )
    const { container } = renderWithProviders(<LoginPage />)

    await user.type(screen.getByRole('textbox'), 'owner@acme.example.com')
    await user.type(container.querySelector('input[type="password"]')!, 'wrong-password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument()
    expect(localStorage.getItem('nuprop_token')).toBeNull()
  })

  it('disables the submit button while signing in', async () => {
    const user = userEvent.setup()
    let resolve: (() => void) | undefined
    server.use(
      http.post(`${API}/auth/login`, async () => {
        await new Promise<void>((r) => {
          resolve = r
        })
        return HttpResponse.json({
          access_token: 'jwt', token_type: 'bearer', user_id: 'u1', agency_id: 'a1',
        })
      }),
    )
    const { container } = renderWithProviders(<LoginPage />)
    await user.type(screen.getByRole('textbox'), 'owner@acme.example.com')
    await user.type(container.querySelector('input[type="password"]')!, 'pw123456')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('button', { name: /signing in/i })).toBeDisabled()
    resolve?.() // let the request finish so the test exits cleanly
  })
})
