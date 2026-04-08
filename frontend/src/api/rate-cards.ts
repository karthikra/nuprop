import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { RateCard, RateCardSummary, RateCardUpdate } from '../types/rate-card'

export function useActiveRateCard() {
  return useQuery({
    queryKey: ['rate-card', 'active'],
    queryFn: async () => {
      const { data } = await api.get<RateCard>('/rate-cards/active')
      return data
    },
  })
}

export function useRateCardVersions() {
  return useQuery({
    queryKey: ['rate-card', 'versions'],
    queryFn: async () => {
      const { data } = await api.get<RateCardSummary[]>('/rate-cards')
      return data
    },
  })
}

export function useUpdateRateCard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...update }: RateCardUpdate & { id: string }) => {
      const { data } = await api.patch<RateCard>(`/rate-cards/${id}`, update)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-card'] }),
  })
}

export function useCreateRateCardVersion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (version: string) => {
      const { data } = await api.post<RateCard>('/rate-cards', { version })
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-card'] }),
  })
}
