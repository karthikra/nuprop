export interface Package {
  base: number
  description: string
  includes?: string
  typical_hours?: number
  deliverable_count?: number
}

export interface Offering {
  name: string
  code: string
  packages: Record<string, Package>
}

export interface Multiplier {
  value: number
  description: string
}

export interface RateCard {
  id: string
  version: string
  is_active: boolean
  offerings: Record<string, Offering>
  hourly_rates: Record<string, number>
  multipliers: Record<string, Multiplier>
  pass_through_markup: number
  standard_options: number
  standard_revisions: number
  created_at: string
  updated_at: string
}

export interface RateCardSummary {
  id: string
  version: string
  is_active: boolean
  created_at: string
}

export interface RateCardUpdate {
  offerings?: Record<string, Offering>
  hourly_rates?: Record<string, number>
  multipliers?: Record<string, Multiplier>
  pass_through_markup?: number
  standard_options?: number
  standard_revisions?: number
}
