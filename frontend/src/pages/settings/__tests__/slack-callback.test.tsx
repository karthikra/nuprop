import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SlackCallbackPage } from '../slack-callback'

describe('SlackCallbackPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the processing state and calls the callback endpoint', async () => {
    let calledWith: Record<string, unknown> | null = null
    server.use(
      http.post(`${API}/connectors/slack/callback`, async ({ request }) => {
        calledWith = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ connected: true, workspace: 'Acme HQ' })
      }),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc123&state=signed.xyz' })
    expect(screen.getByText(/connecting slack/i)).toBeInTheDocument()
    await waitFor(() => expect(calledWith).toEqual({ code: 'abc123', state: 'signed.xyz' }))
  })

  it('shows the success state after callback succeeds', async () => {
    server.use(
      http.post(`${API}/connectors/slack/callback`, () =>
        HttpResponse.json({ connected: true, workspace: 'Acme HQ' }),
      ),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc&state=x' })
    await waitFor(() =>
      expect(screen.getByText(/slack connected/i)).toBeInTheDocument(),
    )
  })

  it('shows the error state when the callback fails', async () => {
    server.use(
      http.post(`${API}/connectors/slack/callback`, () =>
        HttpResponse.json({ detail: 'invalid oauth state (signature_mismatch)' }, { status: 400 }),
      ),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc&state=bad' })
    await waitFor(() =>
      expect(screen.getByText(/failed to connect slack/i)).toBeInTheDocument(),
    )
  })

  it('shows the error state when the code param is missing', async () => {
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback' })
    await waitFor(() =>
      expect(screen.getByText(/failed to connect slack/i)).toBeInTheDocument(),
    )
  })
})
