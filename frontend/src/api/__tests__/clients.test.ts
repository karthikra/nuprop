import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { act, renderHook, waitFor } from '@testing-library/react'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { createTestQueryClient, queryWrapper } from '../../test/utils'
import {
  useClient,
  useClients,
  useCreateClient,
  useDeleteClient,
  useUpdateClient,
} from '../clients'

const sampleClient = {
  id: 'c1', name: 'Acme', slug: 'acme', industry: 'tech', size: 'sme',
  contacts: [], notes: null, tags: ['vip'], context_profile: {},
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

describe('clients API hooks', () => {
  it('useClients fetches the client list', async () => {
    server.use(http.get(`${API}/clients`, () => HttpResponse.json([sampleClient])))
    const { result } = renderHook(() => useClients(), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([sampleClient])
  })

  it('useClients passes the search term as the `q` query param', async () => {
    let receivedQ: string | null = null
    server.use(
      http.get(`${API}/clients`, ({ request }) => {
        receivedQ = new URL(request.url).searchParams.get('q')
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useClients('acme'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(receivedQ).toBe('acme')
  })

  it('useClient fetches a single client by id', async () => {
    server.use(http.get(`${API}/clients/c1`, () => HttpResponse.json(sampleClient)))
    const { result } = renderHook(() => useClient('c1'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.name).toBe('Acme')
  })

  it('useClient stays idle when the id is empty', () => {
    const { result } = renderHook(() => useClient(''), { wrapper: queryWrapper() })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('useCreateClient posts the payload and invalidates the clients query', async () => {
    const qc = createTestQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    let body: unknown = null
    server.use(
      http.post(`${API}/clients`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(sampleClient)
      }),
    )
    const { result } = renderHook(() => useCreateClient(), { wrapper: queryWrapper(qc) })
    await act(async () => {
      await result.current.mutateAsync({ name: 'Acme' })
    })
    expect(body).toEqual({ name: 'Acme' })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['clients'] })
  })

  it('useUpdateClient patches /clients/:id with the id stripped from the body', async () => {
    let url = ''
    let body: unknown = null
    server.use(
      http.patch(`${API}/clients/c1`, async ({ request }) => {
        url = request.url
        body = await request.json()
        return HttpResponse.json(sampleClient)
      }),
    )
    const { result } = renderHook(() => useUpdateClient(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync({ id: 'c1', name: 'Renamed' })
    })
    expect(url).toContain('/clients/c1')
    expect(body).toEqual({ name: 'Renamed' })
  })

  it('useDeleteClient deletes /clients/:id', async () => {
    let called = false
    server.use(
      http.delete(`${API}/clients/c1`, () => {
        called = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { result } = renderHook(() => useDeleteClient(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync('c1')
    })
    expect(called).toBe(true)
  })
})
