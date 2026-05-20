import { useMutation } from '@tanstack/react-query'
import { api } from './client'
import type { DiscoveryResponse, LookbackDays } from '../types/discovery'

export function useDiscoverClients() {
  return useMutation({
    mutationFn: async (lookback_days: LookbackDays) => {
      const { data } = await api.post<DiscoveryResponse>(
        '/connectors/gmail/discover-clients',
        { lookback_days },
      )
      return data
    },
  })
}
