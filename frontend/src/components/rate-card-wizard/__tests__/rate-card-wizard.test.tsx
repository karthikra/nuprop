import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RateCardWizard } from '../rate-card-wizard'

describe('RateCardWizard', () => {
  beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true) })

  it('starts on sub-step 2a (Offerings)', () => {
    render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)
    expect(screen.getByText(/offerings & packages/i)).toBeInTheDocument()
  })

  it('advances through all 4 sub-steps and submits with default empty payload when all are skipped', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/hourly rates by role/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/pricing multipliers/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/defaults & policies/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith({
      version: 'v1',
      offerings: {},
      hourly_rates: {},
      multipliers: {
        urgency_rush: { value: 1.5, description: '' },
        annual_bundle: { value: 0.88, description: '' },
        existing_client: { value: 0.95, description: '' },
        complexity_enterprise: { value: 1.5, description: '' },
      },
      pass_through_markup: 0.10,
      standard_options: 3,
      standard_revisions: 2,
    })
  })

  it('navigates back and preserves prior sub-step state', async () => {
    const user = userEvent.setup()
    render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)

    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('New offering')

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(screen.getByText(/hourly rates by role/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('New offering')
  })

  it('preserves an added offering even with empty packages in the submitted payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      offerings: { O1: { name: 'New offering', code: 'O1', packages: {} } },
    }))
  })

  it('drops fixed-row multipliers with value 0 from the payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))

    const rushInput = screen.getByLabelText(/value for rush job/i)
    await user.clear(rushInput)
    await user.type(rushInput, '0')

    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))

    const payload = onSubmit.mock.calls[0][0]
    expect(payload.multipliers).not.toHaveProperty('urgency_rush')
    expect(payload.multipliers).toHaveProperty('annual_bundle')
    expect(payload.multipliers).toHaveProperty('existing_client')
    expect(payload.multipliers).toHaveProperty('complexity_enterprise')
  })

  it('disables the primary button when saving is true', () => {
    render(<RateCardWizard onSubmit={vi.fn()} saving={true} />)
    expect(screen.getByRole('button', { name: /save & continue/i })).toBeDisabled()
  })
})
