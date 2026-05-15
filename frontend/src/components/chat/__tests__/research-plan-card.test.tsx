import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResearchPlanCard } from '../research-plan-card'
import type { ChatMessage } from '../../../types/proposal'

function planMessage(phase: 'research' | 'benchmarks'): ChatMessage {
  return {
    id: 'pl1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_plan`, content: '',
    extra_data: {
      phase,
      queries: [
        'Pepsi Global rebrand 2024',
        'Pepsi creative agency relationships',
        'FMCG dashboarding benchmarks India',
      ],
      rationale: 'Together these queries cover strategic context and existing agency relationships.',
    },
    phase, created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ResearchPlanCard', () => {
  it('renders the research plan with queries and rationale', () => {
    render(<ResearchPlanCard message={planMessage('research')} />)
    expect(screen.getByText(/Research plan/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi Global rebrand 2024')).toBeInTheDocument()
    expect(screen.getByText('Pepsi creative agency relationships')).toBeInTheDocument()
    expect(screen.getByText('FMCG dashboarding benchmarks India')).toBeInTheDocument()
    expect(screen.getByText(/Together these queries/)).toBeInTheDocument()
  })

  it('uses the benchmarks header when phase=benchmarks', () => {
    render(<ResearchPlanCard message={planMessage('benchmarks')} />)
    expect(screen.getByText(/Benchmarks plan/i)).toBeInTheDocument()
  })
})
