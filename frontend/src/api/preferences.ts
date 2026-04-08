import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Proposal } from '../types/proposal'

export function useUpdatePreferences() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ proposalId, prefs }: { proposalId: string; prefs: Record<string, unknown> }) => {
      const { data } = await api.patch<Proposal>(`/proposals/${proposalId}/preferences`, prefs)
      return data
    },
    onSuccess: (data) => {
      qc.setQueryData(['proposals', data.id], data)
    },
  })
}
