import { http, HttpResponse } from 'msw'

export const API = '/api/v1'

/**
 * Baseline handlers — the "ambient" GETs that several flows touch. Individual
 * tests layer scenario-specific handlers on top with `server.use(...)`.
 */
export const handlers = [
  http.get(`${API}/clients`, () => HttpResponse.json([])),

  http.get(`${API}/auth/me`, () =>
    HttpResponse.json({
      id: 'user-1',
      email: 'owner@acme.example.com',
      full_name: 'Acme Owner',
      agency_id: 'agency-1',
      is_owner: true,
    }),
  ),

  http.get(`${API}/agencies/me`, () =>
    HttpResponse.json({
      id: 'agency-1',
      name: 'Acme Agency',
      slug: 'acme-agency',
      logo_url: null,
      colours: {},
      fonts: {},
      currency: 'INR',
      gst_rate: 0.18,
      payment_terms: {},
      onboarding_complete: true,
    }),
  ),
]
