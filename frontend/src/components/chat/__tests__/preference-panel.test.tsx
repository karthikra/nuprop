import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { PreferencePanel } from '../preference-panel'
import type { Proposal } from '../../../types/proposal'

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: 'prop-1', agency_id: 'a1', client_id: 'c1', project_name: 'P',
    status: 'draft', brief: {}, template_id: null, preferences: {},
    pipeline_state: { current_phase: 'brief', phases_completed: [], context: {} },
    created_at: '', updated_at: '', ...overrides,
  }
}

describe('PreferencePanel', () => {
  it('renders the preference sections', () => {
    renderWithProviders(<PreferencePanel proposal={proposal()} />)
    expect(screen.getByText('Preferences')).toBeInTheDocument()
    expect(screen.getByText('Letter')).toBeInTheDocument()
    expect(screen.getByText('Pricing')).toBeInTheDocument()
    expect(screen.getByText('Output')).toBeInTheDocument()
  })

  it('collapses and re-expands the panel', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PreferencePanel proposal={proposal()} />)
    expect(screen.getByText('Preferences')).toBeInTheDocument()

    await user.click(screen.getByRole('button')) // the only button while expanded — collapse
    expect(screen.queryByText('Preferences')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button')) // the only button while collapsed — expand
    expect(screen.getByText('Preferences')).toBeInTheDocument()
  })

  it('shows the context-aware override banner when overrides exist', () => {
    renderWithProviders(
      <PreferencePanel
        proposal={proposal({
          pipeline_state: {
            current_phase: 'brief',
            phases_completed: [],
            context: {},
            context_overrides: [
              { key: 'letter_strategy', value: 'warm', reason: 'Existing client relationship' },
            ],
          },
        })}
      />,
    )
    expect(screen.getByText('Context-aware')).toBeInTheDocument()
    expect(screen.getByText(/Existing client relationship/)).toBeInTheDocument()
  })

  it('sends a debounced preference update when a select changes', async () => {
    const user = userEvent.setup()
    let body: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/proposals/prop-1/preferences`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(proposal())
      }),
    )
    renderWithProviders(<PreferencePanel proposal={proposal()} />)

    // the first <select> is the letter "Tone" — i.e. letter_strategy
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'warm')

    await waitFor(() => expect(body).toEqual({ letter_strategy: 'warm' }))
  })
})
