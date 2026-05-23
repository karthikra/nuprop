import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { GmailConnectorCard } from '../gmail-connector-card'

describe('GmailConnectorCard', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('shows the loading state while status is being fetched', () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, async () => {
        // Delay so the component renders in loading state
        await new Promise((r) => setTimeout(r, 50))
        return HttpResponse.json({
          connected: false, configured: true, email: null, last_sync: null, email_count: 0,
        })
      }),
    )
    renderWithProviders(<GmailConnectorCard />)
    expect(screen.getByText(/checking connection/i)).toBeInTheDocument()
  })

  it('shows the not-configured amber banner when configured=false', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: false, email: null, last_sync: null, email_count: 0 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText(/GOOGLE_CLIENT_ID/)).toBeInTheDocument(),
    )
  })

  it('shows the Connect Gmail button when configured but not connected', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: true, email: null, last_sync: null, email_count: 0 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect gmail/i })).toBeInTheDocument(),
    )
  })

  it('shows the connected state with sync + disconnect buttons', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({
          connected: true,
          configured: true,
          email: 'owner@acme.example.com',
          last_sync: '2026-05-17T10:00:00Z',
          email_count: 42,
        }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText('owner@acme.example.com')).toBeInTheDocument(),
    )
    expect(screen.getByText('42')).toBeInTheDocument() // email_count
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
  })

  it('renders an inline error when Connect Gmail (getAuthUrl) fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: true, email: null, last_sync: null, email_count: 0 }),
      ),
      http.get(`${API}/connectors/gmail/auth-url`, () =>
        HttpResponse.json({ detail: 'OAuth provider unavailable' }, { status: 500 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    const connectBtn = await screen.findByRole('button', { name: /connect gmail/i })
    await user.click(connectBtn)
    await waitFor(() =>
      expect(screen.getByText(/OAuth provider unavailable/i)).toBeInTheDocument(),
    )
  })

  it('renders an inline error when Disconnect Gmail fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({
          connected: true, configured: true, email: 'me@acme.com', last_sync: null, email_count: 0,
        }),
      ),
      http.delete(`${API}/connectors/gmail`, () =>
        HttpResponse.json({ detail: 'Disconnect failed' }, { status: 500 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    const disconnectBtn = await screen.findByRole('button', { name: /^disconnect$/i })
    await user.click(disconnectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Disconnect failed/i)).toBeInTheDocument(),
    )
  })
})
