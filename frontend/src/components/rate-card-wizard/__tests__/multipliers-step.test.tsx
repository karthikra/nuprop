import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Multiplier } from '../../../types/rate-card'
import { MultipliersStep } from '../multipliers-step'

/** Wrapper so user-event keystrokes propagate via real React re-renders. */
function Wrapper({
  initial = {},
  onChange,
}: {
  initial?: Record<string, Multiplier>
  onChange?: (v: Record<string, Multiplier>) => void
}) {
  const [val, setVal] = useState<Record<string, Multiplier>>(initial)
  return (
    <MultipliersStep
      value={val}
      onChange={(next) => {
        setVal(next)
        onChange?.(next)
      }}
    />
  )
}

describe('MultipliersStep', () => {
  it('renders all 4 fixed rows with their default values', () => {
    render(<Wrapper />)
    expect(screen.getByText('Rush job')).toBeInTheDocument()
    expect(screen.getByText('urgency_rush')).toBeInTheDocument()
    expect(screen.getByText('Annual bundle')).toBeInTheDocument()
    expect(screen.getByText('annual_bundle')).toBeInTheDocument()
    expect(screen.getByText('Existing client')).toBeInTheDocument()
    expect(screen.getByText('Enterprise complexity')).toBeInTheDocument()
    expect(screen.getByLabelText(/value for rush job/i)).toHaveValue(1.5)
    expect(screen.getByLabelText(/value for annual bundle/i)).toHaveValue(0.88)
    expect(screen.getByLabelText(/value for existing client/i)).toHaveValue(0.95)
    expect(screen.getByLabelText(/value for enterprise complexity/i)).toHaveValue(1.5)
  })

  it('uses the existing value if one is already in props', () => {
    render(<Wrapper initial={{ urgency_rush: { value: 2.0, description: 'custom' } }} />)
    expect(screen.getByLabelText(/value for rush job/i)).toHaveValue(2.0)
    expect(screen.getByDisplayValue('custom')).toBeInTheDocument()
  })

  it('calls onChange when a fixed-row value is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper onChange={onChange} />)
    const input = screen.getByLabelText(/value for rush job/i)
    await user.clear(input)
    await user.type(input, '2')
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      urgency_rush: { value: 2, description: '' },
    }))
  })

  it('shows a warning when the Add custom button is clicked', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)
    await user.click(screen.getByRole('button', { name: /add custom multiplier/i }))
    expect(screen.getByText(/cost-model only auto-applies the four above/i)).toBeInTheDocument()
  })

  it('adds a custom multiplier with snake_cased key on commit', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /add custom multiplier/i }))
    await user.type(screen.getByPlaceholderText(/multiplier name/i), 'New Client')
    await user.clear(screen.getByPlaceholderText(/value/i))
    await user.type(screen.getByPlaceholderText(/value/i), '1.2')
    await user.click(screen.getByRole('button', { name: /save custom/i }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      new_client: { value: 1.2, description: '' },
    }))
  })
})
