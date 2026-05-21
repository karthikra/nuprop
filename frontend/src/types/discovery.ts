export interface TopSender {
  name: string
  email: string
  message_count: number
}

export interface Candidate {
  domain: string
  suggested_name: string
  message_count: number
  sender_count: number
  top_senders: TopSender[]
  first_date: string
  last_date: string
}

export interface DiscoveryResponse {
  candidates: Candidate[]
  excluded_existing: number
  scanned_messages: number
  duration_seconds: number
}

export type LookbackDays = 30 | 90 | 365
