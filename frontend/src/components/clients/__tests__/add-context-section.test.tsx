import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AddContextSection } from '../add-context-section'

const STUB_EXTRACTED = {
  relationship: { status: 'existing_client', primary_contact: { name: 'Priya' } },
  past_work: [{ project: 'Brand Sprint', value: 250000, status: 'completed' }],
}

describe('AddContextSection', () => {
  it('starts collapsed and shows an Add button', () => {
    renderWithProviders(<AddContextSection clientId="c1" />)
    expect(screen.getByRole('button', { name: /add or update context/i })).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('expands to a textarea when the Add button is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /extract preview/i })).toBeInTheDocument()
  })

  it('runs preview, shows the extracted structure, then commits on save', async () => {
    const user = userEvent.setup()
    let previewBody: Record<string, unknown> | null = null
    let saveBody: Record<string, unknown> | null = null

    server.use(
      http.post(`${API}/clients/c1/context/preview`, async ({ request }) => {
        previewBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ extracted: STUB_EXTRACTED })
      }),
      http.post(`${API}/clients/c1/context/save`, async ({ request }) => {
        saveBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [],
          context_profile: STUB_EXTRACTED,
          created_at: '', updated_at: '',
        })
      }),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'Met Priya last week, brand sprint went well.')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() =>
      expect(previewBody).toEqual({ raw_text: 'Met Priya last week, brand sprint went well.' }),
    )
    // Preview rendered
    await waitFor(() => expect(screen.getByText(/Priya/i)).toBeInTheDocument())
    expect(screen.getByText(/Brand Sprint/i)).toBeInTheDocument()

    // Save
    await user.click(screen.getByRole('button', { name: /save to client/i }))
    await waitFor(() => expect(saveBody).toEqual({ profile: STUB_EXTRACTED }))

    // Collapses back after save (the "Add" button is visible again)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /add or update context/i })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('preserves the textarea content when "Edit text" is clicked from preview', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/clients/c1/context/preview`, () =>
        HttpResponse.json({ extracted: STUB_EXTRACTED }),
      ),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'first attempt')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() => expect(screen.getByText(/Priya/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /edit text/i }))

    // Textarea reappears, retains content
    expect(screen.getByRole('textbox')).toHaveValue('first attempt')
  })

  it('clears state on Cancel', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'discarded')
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    // Collapsed
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    // Re-expanding shows an empty textarea (state cleared)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('shows an error message when preview fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/clients/c1/context/preview`, () =>
        HttpResponse.json({ detail: 'AI service unavailable' }, { status: 503 }),
      ),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'anything')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() =>
      expect(screen.getByText(/AI service unavailable|extraction failed/i)).toBeInTheDocument(),
    )
    // Textarea still present so user can retry
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('disables the Extract preview button when textarea is empty', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('button', { name: /extract preview/i })).toBeDisabled()

    await user.type(screen.getByRole('textbox'), 'now non-empty')
    expect(screen.getByRole('button', { name: /extract preview/i })).not.toBeDisabled()
  })
})
