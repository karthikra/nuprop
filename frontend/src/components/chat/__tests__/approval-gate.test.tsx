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
    extra_data: { requires_approval: true, brief: { client: { name: 'Acme' } } },
    phase: 'brief', created_at: '2026-01-01T00:00:00Z',
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
    phase: 'template_confirm', created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ApprovalGate', () => {
  it('renders the brief summary with the structured brief JSON', () => {
    render(<ApprovalGate message={briefMessage()} proposalId="prop-1" gateId="brief" />)
    expect(screen.getByText(/Brief Summary/i)).toBeInTheDocument()
    expect(screen.getByText(/"name": "Acme"/)).toBeInTheDocument()
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
