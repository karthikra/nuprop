import type { Offering, Multiplier } from '../../types/rate-card'

/** The exact JSON shape posted to `POST /agencies/me/onboarding` with step=2. */
export interface RateCardPayload {
  version: string
  offerings: Record<string, Offering>
  hourly_rates: Record<string, number>
  multipliers: Record<string, Multiplier>
  pass_through_markup: number
  standard_options: number
  standard_revisions: number
}

/** Defaults applied to any field the user skips. Mirrors agency_viewmodel.py:69-77. */
export const DEFAULT_PAYLOAD: RateCardPayload = {
  version: 'v1',
  offerings: {},
  hourly_rates: {},
  multipliers: {},
  pass_through_markup: 0.10,
  standard_options: 3,
  standard_revisions: 2,
}
