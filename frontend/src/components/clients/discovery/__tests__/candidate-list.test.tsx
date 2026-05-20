import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CandidateList } from '../candidate-list'
import type { Candidate, DiscoveryResponse } from '../../../types/discovery'

const C: Candidate = {
  domain: 'acme.com',
  suggested_name: 'Acme',
  message_count: 47,
  sender_count: 3,
  top_senders: [{ name: 'Jane Doe', email: 'jane@acme.com', message_count: 28 }],
  first_date: '2026-04-01T00:00:00Z',
  last_date: '2026-05-18T00:00:00Z',
}

const D: Candidate = { ...C, domain: 'tatacomms.com', suggested_name: 'Tatacomms', message_count: 32 }

const RESPONSE: DiscoveryResponse = {
  candidates: [C, D],
  excluded_existing: 0,
  scanned_messages: 250,
  duration_seconds: 4.2,
}

describe('CandidateList', () => {
  it('renders one row per candidate with name and counts', () => {
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('Tatacomms')).toBeInTheDocument()
    expect(screen.getByText(/47 emails/)).toBeInTheDocument()
    expect(screen.getByText(/3 senders/)).toBeInTheDocument()
  })

  it('disables the Review button when nothing is selected', () => {
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    expect(screen.getByRole('button', { name: /review/i })).toBeDisabled()
  })

  it('enables the Review button after a candidate is checked', async () => {
    const user = userEvent.setup()
    render(<CandidateList response={RESPONSE} onReview={vi.fn()} onSkipAll={vi.fn()} />)
    const checks = screen.getAllByRole('checkbox')
    await user.click(checks[0])
    expect(screen.getByRole('button', { name: /review 1 selected/i })).toBeEnabled()
  })

  it('calls onReview with the selected candidates', async () => {
    const user = userEvent.setup()
    const onReview = vi.fn()
    render(<CandidateList response={RESPONSE} onReview={onReview} onSkipAll={vi.fn()} />)
    const checks = screen.getAllByRole('checkbox')
    await user.click(checks[0])
    await user.click(checks[1])
    await user.click(screen.getByRole('button', { name: /review 2 selected/i }))
    expect(onReview).toHaveBeenCalledWith([C, D])
  })

  it('renders the excluded_existing note when > 0', () => {
    render(<CandidateList
      response={{ ...RESPONSE, excluded_existing: 3 }}
      onReview={vi.fn()}
      onSkipAll={vi.fn()}
    />)
    expect(screen.getByText(/3 domains already linked/i)).toBeInTheDocument()
  })

  it('renders the no-candidates message when candidates is empty', () => {
    render(<CandidateList
      response={{ candidates: [], excluded_existing: 0, scanned_messages: 47, duration_seconds: 1.2 }}
      onReview={vi.fn()}
      onSkipAll={vi.fn()}
    />)
    expect(screen.getByText(/no client-looking domains/i)).toBeInTheDocument()
  })
})
