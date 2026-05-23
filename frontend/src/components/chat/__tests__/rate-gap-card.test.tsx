import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { RateGapCard } from '../rate-gap-card'

const SAMPLE_GAPS = {
  missing_roles: ['senior_strategist'],
  missing_offerings: ['annual_retainer'],
  needed_roles: ['senior_strategist'],
  needed_offerings: ['annual_retainer'],
}

describe('RateGapCard', () => {
  it('renders one input per missing role and offering', () => {
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)
    expect(screen.getByLabelText(/senior strategist/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/annual retainer/i)).toBeInTheDocument()
  })

  it('submits filled values to /rate-card-gaps/fill', async () => {
    const user = userEvent.setup()
    let body: any = null
    server.use(
      http.post(`${API}/proposals/p1/rate-card-gaps/fill`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    await user.type(screen.getByLabelText(/senior strategist/i), '4500')
    await user.type(screen.getByLabelText(/annual retainer.*price/i), '1500000')

    await user.click(screen.getByRole('button', { name: /fill and continue/i }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body.hourly_rates.senior_strategist).toBe(4500)
    expect(body.offerings.annual_retainer.base_price).toBe(1500000)
  })

  it('calls /rate-card-gaps/skip when Skip is clicked', async () => {
    const user = userEvent.setup()
    let called = false
    server.use(
      http.post(`${API}/proposals/p1/rate-card-gaps/skip`, () => {
        called = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    await user.click(screen.getByRole('button', { name: /skip/i }))
    await waitFor(() => expect(called).toBe(true))
  })

  it('shows the preview after a successful Excel upload, then confirm', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/proposals/p1/rate-card-import`, () =>
        HttpResponse.json({
          hourly_rates: { senior_strategist: 4500 },
          offerings: {},
          multipliers: {},
          low_confidence_fields: [],
        }),
      ),
      http.post(`${API}/proposals/p1/rate-card-import/confirm`, () =>
        HttpResponse.json({ ok: true }),
      ),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    const file = new File(['fake'], 'rates.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const input = screen.getByLabelText(/upload rate card spreadsheet/i) as HTMLInputElement
    await user.upload(input, file)

    await waitFor(() =>
      expect(screen.getByText(/senior_strategist/i)).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() =>
      expect(screen.queryByText(/senior_strategist/i)).not.toBeInTheDocument(),
    )
  })
})
