import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

interface GmailStatus {
  connected: boolean
  configured: boolean
  email: string | null
  last_sync: string | null
  email_count: number
}

interface SyncResult {
  new_emails: number
  total_emails: number
  domains_synced: string[]
  duration_seconds: number
}

export function useGmailStatus() {
  return useQuery({
    queryKey: ['gmail-status'],
    queryFn: async () => {
      const { data } = await api.get<GmailStatus>('/connectors/gmail/status')
      return data
    },
  })
}

export function useGmailAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.get<{ auth_url: string }>('/connectors/gmail/auth-url')
      return data.auth_url
    },
  })
}

export function useGmailCallback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (params: { code: string; state: string }) => {
      const { data } = await api.post<GmailStatus>('/connectors/gmail/callback', params)
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gmail-status'] }),
  })
}

export function useGmailSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SyncResult>('/connectors/gmail/sync')
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gmail-status'] }),
  })
}

export function useGmailDisconnect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.delete('/connectors/gmail')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gmail-status'] }),
  })
}
