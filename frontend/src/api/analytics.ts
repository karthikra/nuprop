import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { OverviewStats, ProposalAnalytics, VisitorSummary } from '../types/analytics'

export function useAnalyticsOverview() {
  return useQuery({
    queryKey: ['analytics', 'overview'],
    queryFn: async () => {
      const { data } = await api.get<OverviewStats>('/analytics/overview')
      return data
    },
  })
}

export function useProposalAnalytics(proposalId: string) {
  return useQuery({
    queryKey: ['analytics', 'proposals', proposalId],
    queryFn: async () => {
      const { data } = await api.get<ProposalAnalytics>(`/analytics/proposals/${proposalId}`)
      return data
    },
    enabled: !!proposalId,
  })
}

export function useProposalVisitors(proposalId: string) {
  return useQuery({
    queryKey: ['analytics', 'proposals', proposalId, 'visitors'],
    queryFn: async () => {
      const { data } = await api.get<VisitorSummary[]>(`/analytics/proposals/${proposalId}/visitors`)
      return data
    },
    enabled: !!proposalId,
  })
}
