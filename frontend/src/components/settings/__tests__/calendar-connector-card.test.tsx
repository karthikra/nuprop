import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { CalendarConnectorCard } from '../calendar-connector-card'

describe('CalendarConnectorCard', () => {
  it('renders the Sync Now button initially with no result', () => {
    renderWithProviders(<CalendarConnectorCard />)
    expect(screen.getByText(/Google Calendar/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.queryByText(/Found/i)).not.toBeInTheDocument()
  })

  it('shows the success result after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ clients_synced: 5, meetings_found: 28 }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 28 meetings across 5 clients/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the backend returns result.error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ error: 'Google not connected' }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Google not connected/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the network request fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ detail: 'Upstream error' }, { status: 503 }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Upstream error|calendar sync failed/i)).toBeInTheDocument(),
    )
  })
})
