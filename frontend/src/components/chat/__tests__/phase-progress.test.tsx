import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { useChatStore } from '../../../stores/chat-store'
import { PhaseProgress } from '../phase-progress'

describe('PhaseProgress', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('renders nothing when jobStatus is null', () => {
    const { container } = renderWithProviders(<PhaseProgress proposalId="p1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the humanized phase label and a running indicator when running', () => {
    useChatStore.setState({
      jobStatus: { phase: 'run_research', state: 'running', updated_at: new Date().toISOString() },
    })
    const { container } = renderWithProviders(<PhaseProgress proposalId="p1" />)
    expect(screen.getByText('Research')).toBeInTheDocument()
    expect(screen.getByText(/running/i)).toBeInTheDocument()
    // spinner present
    expect(container.querySelector('.animate-spin')).not.toBeNull()
  })

  it('shows a complete indicator when complete', () => {
    useChatStore.setState({
      jobStatus: { phase: 'run_research', state: 'complete', updated_at: new Date().toISOString() },
    })
    renderWithProviders(<PhaseProgress proposalId="p1" />)
    expect(screen.getByText('Research')).toBeInTheDocument()
    expect(screen.getByText(/complete/i)).toBeInTheDocument()
  })

  it('shows the error text and a Retry button when failed', () => {
    useChatStore.setState({
      jobStatus: {
        phase: 'run_research',
        state: 'failed',
        error: 'Bedrock timed out',
        updated_at: new Date().toISOString(),
      },
    })
    renderWithProviders(<PhaseProgress proposalId="p1" />)
    expect(screen.getByText('Research')).toBeInTheDocument()
    expect(screen.getByText(/failed/i)).toBeInTheDocument()
    expect(screen.getByText(/bedrock timed out/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('triggers the retry call when Retry is clicked', async () => {
    const user = userEvent.setup()
    let retried = false
    server.use(
      http.post(`${API}/chat/p1/retry`, () => {
        retried = true
        return HttpResponse.json({ ok: true })
      }),
    )
    useChatStore.setState({
      jobStatus: {
        phase: 'run_research',
        state: 'failed',
        error: 'Bedrock timed out',
        updated_at: new Date().toISOString(),
      },
    })
    renderWithProviders(<PhaseProgress proposalId="p1" />)

    await user.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(retried).toBe(true))
  })
})
