import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchActivityLog } from '../research-activity-log'
import type { ChatMessage } from '../../../types/proposal'

function logMessage({
  status = 'running',
  events = [] as Array<Record<string, unknown>>,
  error,
  phase = 'research' as 'research' | 'benchmarks',
}: { status?: string; events?: Array<Record<string, unknown>>; error?: string; phase?: 'research' | 'benchmarks' } = {}): ChatMessage {
  return {
    id: 'log1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_activity_log`, content: '',
    extra_data: { phase, status, events, ...(error ? { error } : {}) },
    phase, channel: 'main', created_at: '2026-01-01T00:00:00Z',
  }
}

describe('ResearchActivityLog', () => {
  it('shows running status + spinner when status=running', () => {
    render(<ResearchActivityLog message={logMessage({
      events: [{ type: 'search', query: 'Pepsi', ts: '2026-01-01T00:00:01Z' }],
    })} />)
    expect(screen.getByText(/research activity/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/running/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi')).toBeInTheDocument()
  })

  it('collapses on status=complete with a one-line summary', () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'complete',
      events: [
        { type: 'search', query: 'q1', ts: 't' },
        { type: 'read', url: 'https://a.com/x', title: 'A', ts: 't' },
        { type: 'read', url: 'https://b.com/y', title: 'B', ts: 't' },
      ],
    })} />)
    expect(screen.getByText(/1 search/i)).toBeInTheDocument()
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument()
  })

  it('stays expanded on status=failed and shows the error', () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'failed',
      error: 'bedrock died',
      events: [{ type: 'search', query: 'q1', ts: 't' }],
    })} />)
    expect(screen.getByLabelText(/failed/i)).toBeInTheDocument()
    expect(screen.getByText('q1')).toBeInTheDocument()
  })

  it('expands the collapsed view when the summary button is clicked', async () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'complete',
      events: [
        { type: 'search', query: 'q1', ts: '2026-01-01T00:00:01Z' },
      ],
    })} />)
    // Collapsed by default — query "q1" is not visible initially.
    expect(screen.queryByText('q1')).not.toBeInTheDocument()
    // Click the summary button to expand.
    await userEvent.click(screen.getByRole('button', { name: /expand activity log/i }))
    expect(screen.getByText('q1')).toBeInTheDocument()
  })
})
