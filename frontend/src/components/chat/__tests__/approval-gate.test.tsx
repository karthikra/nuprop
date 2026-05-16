import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { ApprovalGate } from '../approval-gate'
import type { ChatMessage } from '../../../types/proposal'

function briefMessage(): ChatMessage {
  return {
    id: 'm1', proposal_id: 'prop-1', role: 'assistant', message_type: 'brief_summary',
    content: 'I have gathered the following details about this project.',
    extra_data: {
      requires_approval: true,
      brief: {
        client: { name: 'Acme', industry: 'Beverage', size: 'Enterprise' },
        project: {
          type: 'Rebrand',
          timeline: '8 weeks',
          deliverables: [
            { category: 'Logo', details: 'Primary mark + variants', quantity: 1 },
            { category: 'Brand Guidelines', quantity: 1 },
          ],
        },
        context: {
          relationship: 'cold_pitch',
          urgency: 'medium',
          decision_maker: 'CMO',
        },
      },
    },
    phase: 'brief', channel: 'main', created_at: '2026-01-01T00:00:00Z',
  }
}

function templateMessage(): ChatMessage {
  return {
    id: 'm2', proposal_id: 'prop-1', role: 'assistant', message_type: 'approval_gate',
    content: 'This looks like a Brand Identity project.',
    extra_data: {
      requires_approval: true, gate_type: 'template',
      template_key: 'brand_identity', confidence: 0.8,
    },
    phase: 'template_confirm', channel: 'main', created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ApprovalGate', () => {
  it('renders the brief summary as a structured human-readable card', () => {
    render(<ApprovalGate message={briefMessage()} proposalId="prop-1" gateId="brief" />)
    expect(screen.getByText(/Brief Summary/i)).toBeInTheDocument()

    // Structural: the section labels are uppercased headers in the card.
    expect(screen.getByText('Client')).toBeInTheDocument()
    expect(screen.getByText('Project')).toBeInTheDocument()
    expect(screen.getByText('Context')).toBeInTheDocument()
    expect(screen.getByText('Deliverables')).toBeInTheDocument()

    // Field labels (uppercase) only appear in the rendered card, not raw JSON.
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Industry')).toBeInTheDocument()
    expect(screen.getByText('Timeline')).toBeInTheDocument()

    // Prettified enum: raw JSON has "cold_pitch"; card has "Cold pitch".
    expect(screen.getByText('Cold pitch')).toBeInTheDocument()

    // Data values are reachable (each appears twice — rendered + raw JSON).
    expect(screen.getAllByText('Acme').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Primary mark/).length).toBeGreaterThan(0)

    // Raw JSON details toggle still exposed for power users.
    expect(screen.getByText(/Raw JSON/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approve brief/i })).toBeInTheDocument()
  })

  it('renders template selection with the confidence percentage', () => {
    render(<ApprovalGate message={templateMessage()} proposalId="prop-1" gateId="template" />)
    expect(screen.getByText(/Template Selection/i)).toBeInTheDocument()
    expect(screen.getByText(/Confidence: 80%/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /confirm template/i })).toBeInTheDocument()
  })

  it('approves the brief gate with an empty data payload', async () => {
    const user = userEvent.setup()
    let body: unknown = null
    server.use(
      http.post(`${API}/chat/prop-1/approve/brief`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'msg' })
      }),
    )
    render(<ApprovalGate message={briefMessage()} proposalId="prop-1" gateId="brief" />)
    await user.click(screen.getByRole('button', { name: /approve brief/i }))
    expect(body).toEqual({ data: {} })
    expect(await screen.findByText(/advancing to next phase/i)).toBeInTheDocument()
  })

  it('approves the template gate including the template_key', async () => {
    const user = userEvent.setup()
    let body: { data?: { template_key?: string } } | null = null
    server.use(
      http.post(`${API}/chat/prop-1/approve/template`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json({ id: 'msg' })
      }),
    )
    render(<ApprovalGate message={templateMessage()} proposalId="prop-1" gateId="template" />)
    await user.click(screen.getByRole('button', { name: /confirm template/i }))
    expect(body).toEqual({ data: { template_key: 'brand_identity' } })
  })
})
