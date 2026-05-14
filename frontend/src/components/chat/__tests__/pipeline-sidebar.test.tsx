import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import { useChatStore } from '../../../stores/chat-store'
import { PipelineSidebar } from '../pipeline-sidebar'
import type { Proposal } from '../../../types/proposal'

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: 'prop-1', agency_id: 'a1', client_id: 'c1', project_name: 'Q3 Rebrand',
    status: 'draft', brief: {}, template_id: null, preferences: {},
    pipeline_state: { current_phase: 'research', phases_completed: [], context: {} },
    created_at: '', updated_at: '', ...overrides,
  }
}

describe('PipelineSidebar', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('renders the project name, client and every pipeline phase', () => {
    renderWithProviders(<PipelineSidebar proposal={proposal()} clientName="Acme Co" />)
    expect(screen.getByText('Q3 Rebrand')).toBeInTheDocument()
    expect(screen.getByText('Acme Co')).toBeInTheDocument()
    for (const label of ['Brief', 'Template', 'Research', 'Cost Model', 'Narrative', 'Output', 'Complete']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('emphasises the current phase from the chat store', () => {
    useChatStore.getState().setPipelinePhase('research')
    renderWithProviders(
      <PipelineSidebar
        proposal={proposal({
          pipeline_state: {
            current_phase: 'research',
            phases_completed: ['brief', 'template_confirm'],
            context: {},
          },
        })}
      />,
    )
    expect(screen.getByText('Research')).toHaveClass('font-medium')
  })

  it('shows a stale indicator for completed-but-stale phases', () => {
    const { container } = renderWithProviders(
      <PipelineSidebar
        proposal={proposal({
          pipeline_state: {
            current_phase: 'output_generation',
            phases_completed: ['brief', 'narrative_review'],
            stale_phases: ['narrative_review'],
            context: {},
          },
        })}
      />,
    )
    expect(container.querySelector('[title*="Preferences changed"]')).not.toBeNull()
  })
})
