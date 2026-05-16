import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { act, renderHook, waitFor } from '@testing-library/react'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { createTestQueryClient, queryWrapper } from '../../test/utils'
import {
  useChatMessages,
  useCreateProposal,
  useProposal,
  useProposals,
  useSendMessage,
} from '../proposals'

const sampleProposal = {
  id: 'p1', agency_id: 'a1', client_id: 'c1', project_name: 'Q3 Rebrand',
  status: 'draft', brief: {}, template_id: null, preferences: {},
  pipeline_state: { current_phase: 'brief', phases_completed: [], context: {} },
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

describe('proposals API hooks', () => {
  it('useProposals fetches the proposal list', async () => {
    server.use(http.get(`${API}/proposals`, () => HttpResponse.json([sampleProposal])))
    const { result } = renderHook(() => useProposals(), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })

  it('useProposals forwards the status filter as proposal_status', async () => {
    let received: string | null = null
    server.use(
      http.get(`${API}/proposals`, ({ request }) => {
        received = new URL(request.url).searchParams.get('proposal_status')
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useProposals('sent'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(received).toBe('sent')
  })

  it('useProposal fetches a single proposal by id', async () => {
    server.use(http.get(`${API}/proposals/p1`, () => HttpResponse.json(sampleProposal)))
    const { result } = renderHook(() => useProposal('p1'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.project_name).toBe('Q3 Rebrand')
  })

  it('useCreateProposal posts the payload and invalidates the proposals query', async () => {
    const qc = createTestQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    let body: unknown = null
    server.use(
      http.post(`${API}/proposals`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(sampleProposal)
      }),
    )
    const { result } = renderHook(() => useCreateProposal(), { wrapper: queryWrapper(qc) })
    await act(async () => {
      await result.current.mutateAsync({ client_id: 'c1', project_name: 'Q3 Rebrand' })
    })
    expect(body).toEqual({ client_id: 'c1', project_name: 'Q3 Rebrand' })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['proposals'] })
  })

  it('useChatMessages fetches the message history for a proposal', async () => {
    server.use(
      http.get(`${API}/chat/p1/messages`, () =>
        HttpResponse.json([
          { id: 'm1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: 'hi', extra_data: {}, phase: null, channel: 'main', created_at: '2026-01-01T00:00:00Z' },
        ]),
      ),
    )
    const { result } = renderHook(() => useChatMessages('p1'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })

  it('useSendMessage posts content to the proposal chat channel', async () => {
    let body: unknown = null
    server.use(
      http.post(`${API}/chat/p1/send`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useSendMessage(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync({ proposalId: 'p1', content: 'hello' })
    })
    expect(body).toEqual({ content: 'hello' })
  })
})
