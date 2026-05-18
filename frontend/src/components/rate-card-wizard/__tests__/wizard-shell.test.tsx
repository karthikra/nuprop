import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WizardShell } from '../wizard-shell'

function setup(props: Partial<React.ComponentProps<typeof WizardShell>> = {}) {
  const onSkip = vi.fn()
  const onContinue = vi.fn()
  const onBack = vi.fn()
  render(
    <WizardShell
      subStep={0}
      total={4}
      title="Test step"
      subtitle="Hi"
      onBack={onBack}
      onSkip={onSkip}
      onContinue={onContinue}
      {...props}
    >
      <div data-testid="body">body content</div>
    </WizardShell>,
  )
  return { onBack, onSkip, onContinue }
}

describe('WizardShell', () => {
  it('renders the title, subtitle, and body slot', () => {
    setup()
    expect(screen.getByText('Test step')).toBeInTheDocument()
    expect(screen.getByText('Hi')).toBeInTheDocument()
    expect(screen.getByTestId('body')).toBeInTheDocument()
  })

  it('renders a dot per sub-step with the active one highlighted', () => {
    setup({ subStep: 2, total: 4 })
    const dots = screen.getAllByTestId('wizard-dot')
    expect(dots).toHaveLength(4)
    expect(dots[2]).toHaveAttribute('data-active', 'true')
    expect(dots[0]).toHaveAttribute('data-active', 'false')
  })

  it('hides the Back link when onBack is not provided', () => {
    setup({ onBack: undefined })
    expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
  })

  it('uses the default continue label "Save & Continue"', () => {
    setup()
    expect(screen.getByRole('button', { name: /save & continue/i })).toBeInTheDocument()
  })

  it('uses a custom continue label when provided', () => {
    setup({ continueLabel: 'Finish rate card' })
    expect(screen.getByRole('button', { name: /finish rate card/i })).toBeInTheDocument()
  })

  it('calls onSkip when the skip link is clicked', async () => {
    const user = userEvent.setup()
    const { onSkip } = setup()
    await user.click(screen.getByRole('button', { name: /skip this section/i }))
    expect(onSkip).toHaveBeenCalledOnce()
  })

  it('calls onContinue when the primary button is clicked', async () => {
    const user = userEvent.setup()
    const { onContinue } = setup()
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    expect(onContinue).toHaveBeenCalledOnce()
  })

  it('renders a yellow notice strip when notice prop is set', () => {
    setup({ notice: 'You can fill this in later in Settings' })
    expect(screen.getByText(/fill this in later/i)).toBeInTheDocument()
  })
})
