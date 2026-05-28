import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  Proposal,
  ProposalCreate,
  ProposalListItem,
  ChatMessage,
  Section,
  SectionAsset,
  SectionType,
} from '../types/proposal'

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

export function useIdeationMessages(proposalId: string) {
  return useQuery({
    queryKey: ['ideation-messages', proposalId],
    queryFn: async () => {
      const { data } = await api.get<ChatMessage[]>(`/chat/${proposalId}/ideation/messages`)
      return data
    },
    enabled: !!proposalId,
  })
}

export function useSendIdeationMessage() {
  return useMutation({
    mutationFn: async ({ proposalId, content }: { proposalId: string; content: string }) => {
      const { data } = await api.post<ChatMessage[]>(
        `/chat/${proposalId}/ideation/send`,
        { content },
      )
      return data
    },
  })
}

export function useFillRateCardGaps(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      hourly_rates: Record<string, number>
      offerings: Record<string, { name: string; base_price: number }>
    }) => {
      const { data } = await api.post(
        `/proposals/${proposalId}/rate-card-gaps/fill`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useSkipRateCardGaps(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.post(`/proposals/${proposalId}/rate-card-gaps/skip`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useRetryPhase(proposalId: string) {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/chat/${proposalId}/retry`)
      return data
    },
  })
}

export function useImportRateCardXlsx(proposalId: string) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post(
        `/proposals/${proposalId}/rate-card-import`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return data as {
        hourly_rates: Record<string, number>
        offerings: Record<string, { name: string; base_price: number }>
        multipliers: Record<string, number>
        low_confidence_fields: string[]
      }
    },
  })
}

export function useConfirmRateCardImport(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (preview: {
      hourly_rates: Record<string, number>
      offerings: Record<string, { name: string; base_price: number }>
      multipliers?: Record<string, number>
    }) => {
      await api.post(
        `/proposals/${proposalId}/rate-card-import/confirm`,
        preview,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function usePatchSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      patch: { content?: string; included?: boolean; metadata?: Record<string, unknown> }
    }) => {
      const { data } = await api.patch<Section>(
        `/proposals/${proposalId}/sections/${vars.type}`,
        vars.patch,
      )
      return { type: vars.type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useRegenerateSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (type: SectionType) => {
      const { data } = await api.post<Section>(
        `/proposals/${proposalId}/sections/${type}/regenerate`,
      )
      return { type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useRefineSection(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { type: SectionType; instructions: string }) => {
      const { data } = await api.post<Section>(
        `/proposals/${proposalId}/sections/${vars.type}/refine`,
        { instructions: vars.instructions },
      )
      return { type: vars.type, section: data }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export interface PresignedUpload {
  upload_url: string
  s3_key: string
  asset_id: string
}

export function usePresignAsset(proposalId: string) {
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      kind: 'image' | 'video' | 'audio'
      filename: string
      content_type: string
      size: number
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<PresignedUpload>(
        `/proposals/${proposalId}/sections/${type}/assets/presign`,
        body,
      )
      return data
    },
  })
}

export function useCommitAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      asset_id: string
      s3_key: string
      kind: 'image' | 'video' | 'audio'
      content_type: string
      caption: string | null
      width: number | null
      height: number | null
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<SectionAsset>(
        `/proposals/${proposalId}/sections/${type}/assets/commit`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useGenerateAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      type: SectionType
      kind: 'image' | 'video' | 'audio'
      prompt: string
    }) => {
      const { type, ...body } = vars
      const { data } = await api.post<SectionAsset>(
        `/proposals/${proposalId}/sections/${type}/assets/generate`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}

export function useDeleteAsset(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { type: SectionType; asset_id: string }) => {
      await api.delete(
        `/proposals/${proposalId}/sections/${vars.type}/assets/${vars.asset_id}`,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals', proposalId] }),
  })
}
