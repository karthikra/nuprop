import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../../test/mocks/server'
import { API } from '../../../../test/mocks/handlers'
import { renderWithProviders } from '../../../../test/utils'
import { ClientDiscoveryFlow } from '../client-discovery-flow'

const CANDIDATE_RESPONSE = {
  candidates: [{
    domain: 'acme.com', suggested_name: 'Acme',
    message_count: 47, sender_count: 2,
    top_senders: [{ name: 'Jane', email: 'jane@acme.com', message_count: 28 }],
    first_date: '2026-04-01T00:00:00Z', last_date: '2026-05-18T00:00:00Z',
  }],
  excluded_existing: 0,
  scanned_messages: 200,
  duration_seconds: 4.2,
}

describe('ClientDiscoveryFlow', () => {
  it('walks lookback → scanning → list → wizard → done', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json(CANDIDATE_RESPONSE),
      ),
      http.post(`${API}/clients`, async () =>
        HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '',
        }),
      ),
    )

    const onComplete = vi.fn()
    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={onComplete} />)

    expect(screen.getByText(/look back how far/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /90 days/i }))

    await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /select acme/i }))
    await user.click(screen.getByRole('button', { name: /review 1 selected/i }))

    expect(await screen.findByText(/reviewing 1 of 1/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /save & finish/i }))

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith({ created: 1 }))
  })

  it('shows an error message when the discover call fails with 400', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json(
          { detail: 'Stored Gmail credentials could not be decrypted; please reconnect' },
          { status: 400 },
        ),
      ),
    )

    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))

    await waitFor(() => expect(screen.getByText(/please reconnect/i)).toBeInTheDocument())
  })

  it('Skip all in the candidate list calls onComplete with created=0', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/gmail/discover-clients`, async () =>
        HttpResponse.json(CANDIDATE_RESPONSE),
      ),
    )
    const onComplete = vi.fn()
    renderWithProviders(<ClientDiscoveryFlow open onClose={vi.fn()} onComplete={onComplete} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))
    await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /skip all/i }))
    expect(onComplete).toHaveBeenCalledWith({ created: 0 })
  })
})
