import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { StrategyTemplate } from '../types/template'

export function useTemplates() {
  return useQuery({
    queryKey: ['templates'],
    queryFn: async () => {
      const { data } = await api.get<StrategyTemplate[]>('/templates')
      return data
    },
  })
}

export function useTemplate(id: string) {
  return useQuery({
    queryKey: ['templates', id],
    queryFn: async () => {
      const { data } = await api.get<StrategyTemplate>(`/templates/${id}`)
      return data
    },
    enabled: !!id,
  })
}

export function useUpdateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...update }: { id: string; name?: string; description?: string; category?: string; config?: Record<string, unknown> }) => {
      const { data } = await api.patch<StrategyTemplate>(`/templates/${id}`, update)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates'] }),
  })
}

export function useCloneTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, new_key, new_name }: { id: string; new_key: string; new_name: string }) => {
      const { data } = await api.post<StrategyTemplate>(`/templates/${id}/clone`, { new_key, new_name })
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates'] }),
  })
}

export function useDeleteTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/templates/${id}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates'] }),
  })
}
