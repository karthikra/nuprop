import { describe, it, expect } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { queryWrapper } from '../../test/utils'
import { useIdeationMessages, useSendIdeationMessage } from '../proposals'

describe('ideation hooks', () => {
  it('useIdeationMessages GETs /chat/:id/ideation/messages', async () => {
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () =>
        HttpResponse.json([
          { id: 'i1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: 'hi', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ]),
      ),
    )
    const { result } = renderHook(() => useIdeationMessages('p1'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].channel).toBe('ideation')
  })

  it('useSendIdeationMessage POSTs to /chat/:id/ideation/send', async () => {
    let body: { content?: string } | null = null
    server.use(
      http.post(`${API}/chat/p1/ideation/send`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json([
          { id: 'u1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: body?.content ?? '', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ])
      }),
    )
    const { result } = renderHook(() => useSendIdeationMessage(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync({ proposalId: 'p1', content: 'what if?' })
    })
    expect(body).toEqual({ content: 'what if?' })
  })
})
