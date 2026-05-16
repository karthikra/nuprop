import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchFindingsCard } from '../research-findings-card'
import type { ChatMessage } from '../../../types/proposal'

function findingsMessage({
  phase = 'research' as 'research' | 'benchmarks',
  content = 'Pepsi Global revenue grew 8.2% YoY in Q4 2024. Their last major rebrand was in 2008.',
  citations = [
    { id: 1, url: 'https://reuters.com/a', title: 'Pepsi Q4', domain: 'reuters.com', cited_text: 'Revenue grew 8.2%' },
    { id: 2, url: 'https://brandnew.com/x', title: 'Pepsi 2008 rebrand', domain: 'brandnew.com', cited_text: 'rebrand was in 2008' },
  ],
  spans = [
    { start: 0, end: 47, citation_ids: [1] },
    { start: 49, end: 86, citation_ids: [2] },
  ],
}: { phase?: 'research' | 'benchmarks'; content?: string; citations?: object[]; spans?: object[] } = {}): ChatMessage {
  return {
    id: 'f1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_findings`, content,
    extra_data: { phase, citations, spans },
    phase, channel: 'main', created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ResearchFindingsCard', () => {
  it('renders the markdown body with citation superscripts injected', () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    expect(screen.getByText(/Pepsi Global revenue/)).toBeInTheDocument()
    // Two superscripts — one per span.
    const supers = document.querySelectorAll('sup[data-citation-id]')
    expect(supers.length).toBe(2)
    expect(supers[0].getAttribute('data-citation-id')).toBe('1')
    expect(supers[1].getAttribute('data-citation-id')).toBe('2')
  })

  it('shows the sources list at the bottom with title + domain', () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    expect(screen.getByText(/Sources/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi Q4')).toBeInTheDocument()
    expect(screen.getByText(/reuters.com/)).toBeInTheDocument()
    expect(screen.getByText('Pepsi 2008 rebrand')).toBeInTheDocument()
  })

  it('opens the popover when a superscript is hovered', async () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    const supers = document.querySelectorAll('sup[data-citation-id]')
    await userEvent.hover(supers[0] as Element)
    // Title appears twice (sources list + popover); just check both are present.
    const titles = screen.getAllByText('Pepsi Q4')
    expect(titles.length).toBeGreaterThanOrEqual(2)
  })

  it('uses the benchmarks header when phase=benchmarks', () => {
    render(<ResearchFindingsCard message={findingsMessage({ phase: 'benchmarks' })} />)
    expect(screen.getByText(/Pricing benchmarks/i)).toBeInTheDocument()
  })
})
