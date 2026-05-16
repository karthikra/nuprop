import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { IdeationDrawer } from '../ideation-drawer'
import { useChatStore } from '../../../stores/chat-store'

function wrap(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('IdeationDrawer', () => {
  it('shows the empty state with clickable suggestions on a fresh thread', async () => {
    useChatStore.getState().reset()
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Think out loud/i)).toBeInTheDocument()
    expect(screen.getByText(/What angle should we lead with/)).toBeInTheDocument()

    await userEvent.click(screen.getByText(/What angle should we lead with/))
    const input = screen.getByPlaceholderText(/talk to claude/i) as HTMLTextAreaElement
    expect(input.value).toContain('What angle should we lead with')
  })

  it('renders messages from the ideation slice', async () => {
    useChatStore.getState().reset()
    useChatStore.getState().addMessage({
      id: 'i1', proposal_id: 'p1', role: 'assistant', message_type: 'text',
      content: 'Try the retainer angle.', extra_data: {}, phase: 'ideation',
      created_at: '2026-01-01T00:00:00Z', channel: 'ideation',
    })
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Try the retainer angle/)).toBeInTheDocument()
  })

  it('posts the input to the send endpoint', async () => {
    useChatStore.getState().reset()
    let body: { content?: string } | null = null
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
      http.post(`${API}/chat/p1/ideation/send`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json([
          { id: 'u1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: body?.content ?? '', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ])
      }),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    const input = await screen.findByPlaceholderText(/talk to claude/i)
    await userEvent.type(input, 'will retainer work?')
    await userEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(body).toEqual({ content: 'will retainer work?' })
    expect(await screen.findByText('will retainer work?')).toBeInTheDocument()
  })

  it('renders an inline error block for ideation error messages', async () => {
    useChatStore.getState().reset()
    useChatStore.getState().addMessage({
      id: 'e1', proposal_id: 'p1', role: 'system', message_type: 'text',
      content: "Couldn't reach Bedrock — bedrock down. Send another message to try again.",
      extra_data: { kind: 'error', error: 'bedrock down' },
      phase: 'ideation', created_at: '2026-01-01T00:00:00Z',
      channel: 'ideation',
    })
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Couldn't reach Bedrock/)).toBeInTheDocument()
    expect(screen.getByText(/Couldn't reach Bedrock/).closest('[data-error="ideation"]')).not.toBeNull()
  })
})
