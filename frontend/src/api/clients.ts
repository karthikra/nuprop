import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Client, ClientCreate, ClientUpdate } from '../types/client'

export function useClients(q?: string) {
  return useQuery({
    queryKey: ['clients', q],
    queryFn: async () => {
      const params = q ? { q } : {}
      const { data } = await api.get<Client[]>('/clients', { params })
      return data
    },
  })
}

export function useClient(id: string) {
  return useQuery({
    queryKey: ['clients', id],
    queryFn: async () => {
      const { data } = await api.get<Client>(`/clients/${id}`)
      return data
    },
    enabled: !!id,
  })
}

export function useCreateClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ClientCreate) => {
      const { data } = await api.post<Client>('/clients', payload)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}

export function useUpdateClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }: ClientUpdate & { id: string }) => {
      const { data } = await api.patch<Client>(`/clients/${id}`, payload)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}

export function useDeleteClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/clients/${id}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}


// ── S2: Manual context UI hooks ──────────────────────────────────────────

export interface ContextPreview {
  extracted: Record<string, unknown>
}

export interface ContextBrief {
  brief: string
  has_context: boolean
  email_count: number
}

/** Extract a context structure from raw text WITHOUT persisting. The result
 *  is roundtripped to useContextSave to commit. */
export function useContextPreview(clientId: string) {
  return useMutation({
    mutationFn: async (rawText: string) => {
      const { data } = await api.post<ContextPreview>(
        `/clients/${clientId}/context/preview`,
        { raw_text: rawText },
      )
      return data
    },
  })
}

/** Merge a previously-previewed profile into the client's existing
 *  context_profile. Invalidates the client + brief + intelligence queries. */
export function useContextSave(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (profile: Record<string, unknown>) => {
      const { data } = await api.post<Client>(
        `/clients/${clientId}/context/save`,
        { profile },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-intelligence', clientId] })
      qc.invalidateQueries({ queryKey: ['client-context-brief', clientId] })
    },
  })
}

/** Reset the entire context_profile to {} via PATCH /clients/{id}. */
export function useResetContext(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.patch<Client>(`/clients/${clientId}`, {
        context_profile: {},
      })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-intelligence', clientId] })
      qc.invalidateQueries({ queryKey: ['client-context-brief', clientId] })
    },
  })
}

/** On-demand fetch of the natural-language context brief. Caller passes
 *  `enabled` so the query only runs when the toggle is open. */
export function useContextBrief(clientId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['client-context-brief', clientId],
    queryFn: async () => {
      const { data } = await api.get<ContextBrief>(
        `/clients/${clientId}/context-brief`,
      )
      return data
    },
    enabled: !!clientId && enabled,
  })
}
