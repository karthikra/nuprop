import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SlackConnectorCard } from '../slack-connector-card'

describe('SlackConnectorCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the not-configured message when configured=false', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: false, workspace: null, last_sync: null }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText(/SLACK_CLIENT_ID/)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /connect slack/i })).not.toBeInTheDocument()
  })

  it('shows Connect Slack button when configured but not connected', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect slack/i })).toBeInTheDocument(),
    )
  })

  it('opens the popup with the returned auth URL when Connect Slack is clicked', async () => {
    const user = userEvent.setup()
    const windowOpen = vi.fn()
    vi.stubGlobal('open', windowOpen)
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
      http.get(`${API}/connectors/slack/auth-url`, () =>
        HttpResponse.json({ auth_url: 'https://slack.com/oauth/v2/authorize?state=signed.abc' }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect slack/i })).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /connect slack/i }))
    await waitFor(() =>
      expect(windowOpen).toHaveBeenCalledWith(
        'https://slack.com/oauth/v2/authorize?state=signed.abc',
        'slack-auth',
        expect.any(String),
      ),
    )
  })

  it('shows the connected state with workspace + sync + disconnect buttons', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: '2026-05-17T10:00:00Z' }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^sync$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
  })

  it('renders a green alert with mentions_found after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: '2026-05-17T10:00:00Z' }),
      ),
      http.post(`${API}/connectors/slack/sync`, () =>
        HttpResponse.json({ clients_synced: 2, mentions_found: 7 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^sync$/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 7 mentions across 2 clients/i)).toBeInTheDocument(),
    )
  })

  it('calls DELETE /connectors/slack when Disconnect is confirmed', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: null }),
      ),
      http.delete(`${API}/connectors/slack`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /disconnect/i }))
    await waitFor(() => expect(deleted).toBe(true))
  })

  it('does NOT call DELETE when the user cancels the confirm dialog', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: null }),
      ),
      http.delete(`${API}/connectors/slack`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))

    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /disconnect/i }))
    await new Promise((r) => setTimeout(r, 50))
    expect(deleted).toBe(false)
  })

  it('renders an inline error when Connect Slack (getAuthUrl) fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
      http.get(`${API}/connectors/slack/auth-url`, () =>
        HttpResponse.json({ detail: 'Slack OAuth provider unavailable' }, { status: 500 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    const connectBtn = await screen.findByRole('button', { name: /connect slack/i })
    await user.click(connectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Slack OAuth provider unavailable/i)).toBeInTheDocument(),
    )
  })

  it('renders an inline error when Disconnect Slack fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({
          connected: true, configured: true, workspace: 'acme-team', last_sync: null,
        }),
      ),
      http.delete(`${API}/connectors/slack`, () =>
        HttpResponse.json({ detail: 'Slack disconnect failed' }, { status: 500 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    const disconnectBtn = await screen.findByRole('button', { name: /^disconnect$/i })
    await user.click(disconnectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Slack disconnect failed/i)).toBeInTheDocument(),
    )
  })
})
