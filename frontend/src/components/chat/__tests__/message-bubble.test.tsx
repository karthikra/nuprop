import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from '../message-bubble'
import type { ChatMessage } from '../../../types/proposal'

function base(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'm1', proposal_id: 'prop-1', role: 'assistant', message_type: 'text',
    content: 'plain message', extra_data: {}, phase: null,
    created_at: '2026-01-01T12:30:00Z', ...overrides,
  }
}

describe('MessageBubble', () => {
  it('renders a system message as a centered note', () => {
    render(<MessageBubble message={base({ role: 'system', content: 'phase changed' })} proposalId="prop-1" />)
    expect(screen.getByText('phase changed')).toBeInTheDocument()
  })

  it('renders a plain assistant text message', () => {
    render(<MessageBubble message={base({ content: 'hello there' })} proposalId="prop-1" />)
    expect(screen.getByText('hello there')).toBeInTheDocument()
  })

  it('routes a brief_summary message to the approval gate', () => {
    render(
      <MessageBubble
        message={base({
          message_type: 'brief_summary',
          extra_data: { requires_approval: true },
          content: 'brief text',
        })}
        proposalId="prop-1"
      />,
    )
    expect(screen.getByText(/Brief Summary — Review & Approve/i)).toBeInTheDocument()
  })

  it('routes a cost_model message to the interactive cost-model card', () => {
    render(
      <MessageBubble
        message={base({
          message_type: 'cost_model',
          extra_data: {
            requires_approval: true,
            cost_model: {
              line_items: [], subtotal: 0, discount_percent: 0, discount_amount: 0,
              total: 0, gst_rate: 0.18, gst_amount: 0, grand_total: 0, currency: 'INR',
              multipliers_applied: [],
            },
          },
        })}
        proposalId="prop-1"
      />,
    )
    expect(screen.getByText(/Cost Model — Review & Approve/i)).toBeInTheDocument()
  })

  it('routes a research_findings message to the research findings card', () => {
    render(
      <MessageBubble
        message={base({ message_type: 'research_findings', content: 'we found things' })}
        proposalId="prop-1"
      />,
    )
    expect(screen.getByText(/Research findings/i)).toBeInTheDocument()
    expect(screen.getByText('we found things')).toBeInTheDocument()
  })
})
