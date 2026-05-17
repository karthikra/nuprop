import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ContextProfileCard } from '../context-profile-card'

const populatedProfile = {
  relationship: { status: 'existing_client' },
  pricing_intelligence: { price_sensitivity: 'high' },
  past_work: [{ project: 'Q4 Brand Sprint', value: 250000, status: 'completed' }],
  risks: [{ signal: 'budget tight this quarter' }],
}

describe('ContextProfileCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns nothing for an empty profile', () => {
    const { container } = renderWithProviders(<ContextProfileCard profile={{}} clientId="c1" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the populated profile fields', () => {
    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    expect(screen.getByText(/existing_client/i)).toBeInTheDocument()
    expect(screen.getByText(/high/i)).toBeInTheDocument()
    expect(screen.getByText(/Q4 Brand Sprint/i)).toBeInTheDocument()
    expect(screen.getByText(/budget tight/i)).toBeInTheDocument()
  })

  it('exposes the brief toggle for populated profiles', () => {
    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    expect(screen.getByRole('button', { name: /show what the AI sees/i })).toBeInTheDocument()
  })

  it('shows a reset button that confirms then PATCHes context_profile to {}', async () => {
    const user = userEvent.setup()
    let patchedBody: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/clients/c1`, async ({ request }) => {
        patchedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '',
        })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /reset context/i }))
    await waitFor(() => expect(patchedBody).toEqual({ context_profile: {} }))
  })

  it('does NOT reset when the user cancels the confirm dialog', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.patch(`${API}/clients/c1`, () => {
        calls += 1
        return HttpResponse.json({})
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))

    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /reset context/i }))
    // Give the click handler a tick
    await new Promise((r) => setTimeout(r, 50))
    expect(calls).toBe(0)
  })
})
