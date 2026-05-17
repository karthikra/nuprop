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


// ── S3: Drive/Calendar/Slack hooks ───────────────────────────────────────

export interface DriveSyncResult {
  clients_synced?: number
  documents_found?: number
  error?: string
}

export interface CalendarSyncResult {
  clients_synced?: number
  meetings_found?: number
  error?: string
}

export interface SlackStatus {
  connected: boolean
  configured: boolean
  workspace: string | null
  last_sync: string | null
}

export interface SlackSyncResult {
  clients_synced?: number
  mentions_found?: number
  error?: string
}

/** Sync Drive documents. Rides on Gmail's Google OAuth — only callable when
 *  Gmail is connected. The backend returns `{error: string}` on soft failures
 *  (e.g., "Google not connected") instead of a 4xx, so the caller must render
 *  both `mutation.isError` and `mutation.data?.error`. */
export function useDriveSync() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<DriveSyncResult>('/connectors/drive/sync')
      return data
    },
  })
}

/** Sync Calendar meetings. Same soft-error caveat as Drive. */
export function useCalendarSync() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<CalendarSyncResult>('/connectors/calendar/sync')
      return data
    },
  })
}

export function useSlackStatus() {
  return useQuery({
    queryKey: ['slack-status'],
    queryFn: async () => {
      const { data } = await api.get<SlackStatus>('/connectors/slack/status')
      return data
    },
  })
}

export function useSlackAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.get<{ auth_url: string }>('/connectors/slack/auth-url')
      return data.auth_url
    },
  })
}

export function useSlackCallback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (params: { code: string; state: string }) => {
      const { data } = await api.post<{ connected: boolean; workspace: string }>(
        '/connectors/slack/callback',
        params,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}

export function useSlackSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SlackSyncResult>('/connectors/slack/sync')
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}

export function useSlackDisconnect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.delete('/connectors/slack')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}
