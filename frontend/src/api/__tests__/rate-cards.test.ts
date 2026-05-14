import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { act, renderHook, waitFor } from '@testing-library/react'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { createTestQueryClient, queryWrapper } from '../../test/utils'
import {
  useActiveRateCard,
  useCreateRateCardVersion,
  useRateCardVersions,
  useUpdateRateCard,
} from '../rate-cards'

const sampleRateCard = {
  id: 'rc1', version: 'v1', is_active: true, offerings: {}, hourly_rates: { design: 5000 },
  multipliers: {}, pass_through_markup: 0.1, standard_options: 3, standard_revisions: 2,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

describe('rate-cards API hooks', () => {
  it('useActiveRateCard fetches the active rate card', async () => {
    server.use(http.get(`${API}/rate-cards/active`, () => HttpResponse.json(sampleRateCard)))
    const { result } = renderHook(() => useActiveRateCard(), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.version).toBe('v1')
  })

  it('useRateCardVersions fetches all versions', async () => {
    server.use(
      http.get(`${API}/rate-cards`, () =>
        HttpResponse.json([
          { id: 'rc2', version: 'v2', is_active: true, created_at: '2026-02-01T00:00:00Z' },
          { id: 'rc1', version: 'v1', is_active: false, created_at: '2026-01-01T00:00:00Z' },
        ]),
      ),
    )
    const { result } = renderHook(() => useRateCardVersions(), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
  })

  it('useUpdateRateCard patches /rate-cards/:id with the id stripped from the body', async () => {
    const qc = createTestQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    let url = ''
    let body: unknown = null
    server.use(
      http.patch(`${API}/rate-cards/rc1`, async ({ request }) => {
        url = request.url
        body = await request.json()
        return HttpResponse.json(sampleRateCard)
      }),
    )
    const { result } = renderHook(() => useUpdateRateCard(), { wrapper: queryWrapper(qc) })
    await act(async () => {
      await result.current.mutateAsync({ id: 'rc1', pass_through_markup: 0.15 })
    })
    expect(url).toContain('/rate-cards/rc1')
    expect(body).toEqual({ pass_through_markup: 0.15 })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['rate-card'] })
  })

  it('useCreateRateCardVersion posts the new version label', async () => {
    let body: unknown = null
    server.use(
      http.post(`${API}/rate-cards`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(sampleRateCard)
      }),
    )
    const { result } = renderHook(() => useCreateRateCardVersion(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync('v2')
    })
    expect(body).toEqual({ version: 'v2' })
  })
})
