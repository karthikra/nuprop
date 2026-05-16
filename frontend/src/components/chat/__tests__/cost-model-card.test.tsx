import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { CostModelCard } from '../cost-model-card'
import type { ChatMessage } from '../../../types/proposal'

const costModel = {
  line_items: [
    {
      deliverable: 'Logo', package_id: 'p1', package_name: 'Logo pkg',
      match_quality: 'exact', quantity: 1, unit_cost: 100000, total: 100000, notes: '',
    },
  ],
  subtotal: 100000, discount_percent: 0, discount_amount: 0, total: 100000,
  gst_rate: 0.18, gst_amount: 18000, grand_total: 200000, currency: 'INR',
  multipliers_applied: ['existing_client'],
}

function message(extra_data: Record<string, unknown> = { cost_model: costModel, requires_approval: true }): ChatMessage {
  return {
    id: 'm1', proposal_id: 'prop-1', role: 'assistant', message_type: 'cost_model',
    content: 'cost model', extra_data, phase: 'cost_model_review', channel: 'main',
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('CostModelCard', () => {
  it('renders the line items, summary and applied multipliers', () => {
    render(<CostModelCard message={message()} proposalId="prop-1" />)
    expect(screen.getByText('Logo')).toBeInTheDocument()
    expect(screen.getByText('Grand Total: ₹2.0 L')).toBeInTheDocument()
    expect(screen.getByText(/Multipliers: existing_client/)).toBeInTheDocument()
  })

  it('renders nothing when the message carries no cost model', () => {
    const { container } = render(<CostModelCard message={message({})} proposalId="prop-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('patches a quantity edit and re-renders with the server response', async () => {
    const user = userEvent.setup()
    let patchBody: { index: number; field: string; value: number } | null = null
    server.use(
      http.patch(`${API}/chat/prop-1/cost-model`, async ({ request }) => {
        patchBody = (await request.json()) as typeof patchBody
        return HttpResponse.json({
          ...costModel,
          line_items: [{ ...costModel.line_items[0], quantity: 3, total: 300000 }],
          subtotal: 300000, total: 300000, grand_total: 500000,
        })
      }),
    )
    render(<CostModelCard message={message()} proposalId="prop-1" />)

    await user.click(screen.getByText('1')) // the quantity cell
    const input = screen.getByRole('spinbutton')
    // jsdom doesn't support text selection on number inputs, so set the value
    // directly rather than via user.clear()/user.type()
    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // findByText waits for the PATCH to resolve and the card to re-render
    expect(await screen.findByText('Grand Total: ₹5.0 L')).toBeInTheDocument()
    expect(patchBody).toEqual({ index: 0, field: 'quantity', value: 3 })
  })

  it('approves the cost model', async () => {
    const user = userEvent.setup()
    let approved = false
    server.use(
      http.post(`${API}/chat/prop-1/approve/cost_model`, () => {
        approved = true
        return HttpResponse.json({ id: 'msg' })
      }),
    )
    render(<CostModelCard message={message()} proposalId="prop-1" />)
    await user.click(screen.getByRole('button', { name: /approve cost model/i }))
    expect(approved).toBe(true)
    expect(await screen.findByText(/advancing to narrative generation/i)).toBeInTheDocument()
  })
})
