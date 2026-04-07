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
