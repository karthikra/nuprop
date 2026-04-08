import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { NotificationList, Notification } from '../types/notification'

export function useNotifications(skip = 0, limit = 20) {
  return useQuery({
    queryKey: ['notifications', skip, limit],
    queryFn: async () => {
      const { data } = await api.get<NotificationList>('/notifications', {
        params: { skip, limit },
      })
      return data
    },
  })
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: async () => {
      const { data } = await api.get<{ count: number }>('/notifications/unread-count')
      return data.count
    },
    refetchInterval: 30_000,
  })
}

export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.patch<Notification>(`/notifications/${id}/read`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}
