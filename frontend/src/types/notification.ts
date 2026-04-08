export interface Notification {
  id: string
  proposal_id: string
  alert_type: string
  message: string
  urgency: 'normal' | 'high'
  sent_at: string
  read_at: string | null
}

export interface NotificationList {
  items: Notification[]
  total: number
  unread_count: number
}
