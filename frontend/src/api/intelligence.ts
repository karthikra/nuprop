import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export interface QualityScore {
  recency: number
  volume: number
  depth: number
  breadth: number
  past_work: number
  decision_chain: number
  total: number
  level: string
  description: string
}

export interface PreferenceOverride {
  key: string
  value: string
  reason: string
  confidence: string
}

export interface SentimentEvent {
  date: string
  sentiment: string
  event: string
}

export interface ClientIntelligence {
  quality_score: QualityScore
  preference_overrides: PreferenceOverride[]
  sentiment_timeline: SentimentEvent[]
  source_breakdown: Record<string, number>
}

export function useClientIntelligence(clientId: string) {
  return useQuery({
    queryKey: ['client-intelligence', clientId],
    queryFn: async () => {
      const { data } = await api.get<ClientIntelligence>(`/clients/${clientId}/intelligence`)
      return data
    },
    enabled: !!clientId,
  })
}
