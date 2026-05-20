import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CandidateReviewWizard } from '../candidate-review-wizard'
import type { Candidate } from '../../../types/discovery'

const A: Candidate = {
  domain: 'acme.com', suggested_name: 'Acme',
  message_count: 47, sender_count: 2,
  top_senders: [
    { name: 'Jane', email: 'jane@acme.com', message_count: 28 },
    { name: 'Bob',  email: 'bob@acme.com',  message_count: 19 },
  ],
  first_date: '2026-04-01T00:00:00Z', last_date: '2026-05-18T00:00:00Z',
}
const B: Candidate = { ...A, domain: 'tatacomms.com', suggested_name: 'Tatacomms' }

describe('CandidateReviewWizard', () => {
  it('renders the first candidate with name pre-filled and contacts populated', () => {
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={vi.fn()}
      onComplete={vi.fn()}
    />)
    expect(screen.getByText(/reviewing 1 of 2/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Acme')).toBeInTheDocument()
    expect(screen.getByDisplayValue('jane@acme.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('bob@acme.com')).toBeInTheDocument()
  })

  it('Skip advances to next candidate without saving', async () => {
    const user = userEvent.setup()
    const onSaveClient = vi.fn()
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={onSaveClient}
      onComplete={vi.fn()}
    />)
    await user.click(screen.getByRole('button', { name: /skip this/i }))
    expect(onSaveClient).not.toHaveBeenCalled()
    expect(screen.getByText(/reviewing 2 of 2/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Tatacomms')).toBeInTheDocument()
  })

  it('Save & Next saves then advances', async () => {
    const user = userEvent.setup()
    const onSaveClient = vi.fn().mockResolvedValue(undefined)
    render(<CandidateReviewWizard
      candidates={[A, B]}
      onSaveClient={onSaveClient}
      onComplete={vi.fn()}
    />)
    await user.click(screen.getByRole('button', { name: /save & next/i }))
    expect(onSaveClient).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Acme',
      contacts: [
        { name: 'Jane', email: 'jane@acme.com' },
        { name: 'Bob',  email: 'bob@acme.com'  },
      ],
    }))
    expect(await screen.findByText(/reviewing 2 of 2/i)).toBeInTheDocument()
  })

  it('on final candidate, primary button reads "Save & Finish"', () => {
    render(<CandidateReviewWizard
      candidates={[A]}
      onSaveClient={vi.fn()}
      onComplete={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: /save & finish/i })).toBeInTheDocument()
  })

  it('after final save, onComplete fires with created count', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<CandidateReviewWizard
      candidates={[A]}
      onSaveClient={vi.fn().mockResolvedValue(undefined)}
      onComplete={onComplete}
    />)
    await user.click(screen.getByRole('button', { name: /save & finish/i }))
    expect(onComplete).toHaveBeenCalledWith({ created: 1 })
  })
})
