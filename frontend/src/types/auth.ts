export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  agency_id: string
}

export interface UserResponse {
  id: string
  email: string
  full_name: string
  agency_id: string
  is_owner: boolean
}

export interface AgencyResponse {
  id: string
  name: string
  slug: string
  logo_url: string | null
  colours: Record<string, string>
  fonts: Record<string, string>
  currency: string
  gst_rate: number
  payment_terms: Record<string, unknown>
  onboarding_complete: boolean
}
