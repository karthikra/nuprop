import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StepRateCard } from '../step-rate-card'

describe('StepRateCard (onboarding step 2)', () => {
  beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true) })

  it('renders the rate-card wizard, not a JSON textarea', () => {
    render(<StepRateCard onSubmit={vi.fn()} saving={false} />)
    // No JSON textarea
    expect(screen.queryByPlaceholderText(/version/i)).not.toBeInTheDocument()
    // Wizard chrome is present
    expect(screen.getByText(/offerings & packages/i)).toBeInTheDocument()
  })

  it('forwards the submitted payload through onSubmit when the user skips every sub-step', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<StepRateCard onSubmit={onSubmit} saving={false} />)
    // Skip 3 times to reach 2d
    for (let i = 0; i < 3; i++) {
      await user.click(screen.getByRole('button', { name: /save & continue/i }))
    }
    await user.click(screen.getByRole('button', { name: /finish rate card/i }))
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      version: 'v1',
      offerings: {},
      hourly_rates: {},
      pass_through_markup: 0.10,
    })
  })
})
