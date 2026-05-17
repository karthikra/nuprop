import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ContextBriefToggle } from '../context-brief-toggle'

describe('ContextBriefToggle', () => {
  it('shows the toggle button collapsed by default and does NOT fetch', async () => {
    let fetched = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        fetched += 1
        return HttpResponse.json({ brief: 'Should not be called', has_context: true, email_count: 0 })
      }),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    expect(screen.getByRole('button', { name: /show what the AI sees/i })).toBeInTheDocument()
    // Brief content NOT rendered
    expect(screen.queryByText(/Should not be called/i)).not.toBeInTheDocument()
    // And no network call made
    expect(fetched).toBe(0)
  })

  it('fetches and renders the brief when expanded', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () =>
        HttpResponse.json({
          brief: 'This client is an existing partner. Tone: warm.',
          has_context: true,
          email_count: 0,
        }),
      ),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() =>
      expect(screen.getByText(/existing partner/i)).toBeInTheDocument(),
    )
  })

  it('does not refetch on close + reopen (cached)', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        calls += 1
        return HttpResponse.json({ brief: 'cached brief', has_context: true, email_count: 0 })
      }),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/cached brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)

    // Close — the same button now reads "Hide"
    await user.click(screen.getByRole('button', { name: /hide what the AI sees/i }))
    expect(screen.queryByText(/cached brief/i)).not.toBeInTheDocument()

    // Reopen — should serve from cache, no second network call
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/cached brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)
  })

  it('renders an empty-state message when has_context is false', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () =>
        HttpResponse.json({ brief: '', has_context: false, email_count: 0 }),
      ),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() =>
      expect(screen.getByText(/no context to summarise/i)).toBeInTheDocument(),
    )
  })
})
