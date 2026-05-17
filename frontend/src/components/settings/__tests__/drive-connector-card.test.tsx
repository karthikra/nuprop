import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { DriveConnectorCard } from '../drive-connector-card'

describe('DriveConnectorCard', () => {
  it('renders the Sync Now button initially with no result', () => {
    renderWithProviders(<DriveConnectorCard />)
    expect(screen.getByText(/Google Drive/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.queryByText(/Found/i)).not.toBeInTheDocument()
  })

  it('shows the success result after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ clients_synced: 3, documents_found: 12 }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 12 documents across 3 clients/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the backend returns result.error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ error: 'Google not connected' }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Google not connected/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the network request fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ detail: 'AI service unavailable' }, { status: 503 }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/AI service unavailable|drive sync failed/i)).toBeInTheDocument(),
    )
  })
})
