import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Proposal, ProposalCreate, ProposalListItem, ChatMessage } from '../types/proposal'

export function useProposals(status?: string) {
  return useQuery({
    queryKey: ['proposals', status],
    queryFn: async () => {
      const params = status ? { proposal_status: status } : {}
      const { data } = await api.get<ProposalListItem[]>('/proposals', { params })
      return data
    },
  })
}

export function useProposal(id: string) {
  return useQuery({
    queryKey: ['proposals', id],
    queryFn: async () => {
      const { data } = await api.get<Proposal>(`/proposals/${id}`)
      return data
    },
    enabled: !!id,
  })
}

export function useCreateProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ProposalCreate) => {
      const { data } = await api.post<Proposal>('/proposals', payload)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals'] }),
  })
}

export function useChatMessages(proposalId: string) {
  return useQuery({
    queryKey: ['chat-messages', proposalId],
    queryFn: async () => {
      const { data } = await api.get<ChatMessage[]>(`/chat/${proposalId}/messages`)
      return data
    },
    enabled: !!proposalId,
  })
}

export function useSendMessage() {
  return useMutation({
    mutationFn: async ({ proposalId, content }: { proposalId: string; content: string }) => {
      const { data } = await api.post<ChatMessage[]>(`/chat/${proposalId}/send`, { content })
      return data
    },
  })
}
