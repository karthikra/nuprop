export interface EngagementBreakdown {
  opened_within_24h: number
  time_on_site: number
  sections_viewed: number
  cards_expanded: number
  investment_time: number
  pdf_downloaded: number
  return_visits: number
  cta_clicked: number
  total: number
  classification: string
}

export interface VisitorSummary {
  id: string
  fingerprint: string
  first_seen: string
  last_seen: string
  session_count: number
  total_time_seconds: number
  max_scroll_depth: number
  device_types: string[]
  locations: string[]
  engagement_score: number
  classification: string
}

export interface SectionHeatmapItem {
  section_id: string
  total_time_seconds: number
  unique_visitors: number
  avg_time_seconds: number
}

export interface ProposalAnalytics {
  proposal_id: string
  project_name: string
  client_name: string
  status: string
  total_views: number
  unique_visitors: number
  avg_time_seconds: number
  scroll_depth_distribution: Record<string, number>
  most_viewed_sections: SectionHeatmapItem[]
  most_expanded_cards: { card_id: string; expand_count: number }[]
  engagement_score: number
  engagement_breakdown: EngagementBreakdown
  sent_at: string | null
  last_viewed_at: string | null
}

export interface ProposalAnalyticsListItem {
  proposal_id: string
  project_name: string
  client_name: string
  status: string
  engagement_score: number
  unique_visitors: number
  last_viewed_at: string | null
  sent_at: string | null
}

export interface OverviewStats {
  total_proposals: number
  proposals_sent: number
  proposals_viewed_today: number
  avg_engagement_score: number
  proposals_by_status: Record<string, number>
  win_rate: number | null
  recent_proposals: ProposalAnalyticsListItem[]
}
