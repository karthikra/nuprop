import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { GmailConnectorCard } from '../gmail-connector-card'

describe('GmailConnectorCard', () => {
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
})
