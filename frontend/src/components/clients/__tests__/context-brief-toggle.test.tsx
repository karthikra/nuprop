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

  it('clears the local cache when clientId prop changes', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () =>
        HttpResponse.json({ brief: 'brief for c1', has_context: true, email_count: 0 }),
      ),
      http.get(`${API}/clients/c2/context-brief`, () =>
        HttpResponse.json({ brief: 'brief for c2', has_context: true, email_count: 0 }),
      ),
    )
    const { rerender } = renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/brief for c1/i)).toBeInTheDocument())

    // Switch to client c2 — re-render with new prop
    rerender(<ContextBriefToggle clientId="c2" />)
    // Cache resets, query refires for c2 because open is still true
    await waitFor(() => expect(screen.getByText(/brief for c2/i)).toBeInTheDocument())
    // The previous client's brief must NOT be rendered
    expect(screen.queryByText(/brief for c1/i)).not.toBeInTheDocument()
  })

  it('refetches the brief after the query is invalidated (e.g. after context save/reset)', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        calls += 1
        return HttpResponse.json({
          brief: calls === 1 ? 'first brief' : 'second brief',
          has_context: true,
          email_count: 0,
        })
      }),
    )
    const { queryClient } = renderWithProviders(<ContextBriefToggle clientId="c1" />)

    // Open the toggle — first fetch.
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/first brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)

    // Close the toggle.
    await user.click(screen.getByRole('button', { name: /hide what the AI sees/i }))

    // Simulate a context-save / context-reset mutation invalidating the brief query.
    await queryClient.invalidateQueries({ queryKey: ['client-context-brief', 'c1'] })

    // Reopen — must refetch because the query is now stale.
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/second brief/i)).toBeInTheDocument())
    expect(calls).toBe(2)
  })
})
