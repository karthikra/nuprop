import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HourlyRatesStep } from '../hourly-rates-step'

/** Wrapper so user-event keystrokes propagate via real React re-renders. */
function Wrapper({
  initial = {},
  onChange,
}: {
  initial?: Record<string, number>
  onChange?: (v: Record<string, number>) => void
}) {
  const [val, setVal] = useState<Record<string, number>>(initial)
  return (
    <HourlyRatesStep
      value={val}
      onChange={(next) => {
        setVal(next)
        onChange?.(next)
      }}
    />
  )
}

describe('HourlyRatesStep', () => {
  it('renders 8 common-role chips when value is empty', () => {
    render(<Wrapper />)
    expect(screen.getByRole('button', { name: /\+ creative director/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+ developer/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^\+ (?!add)/i }).length).toBe(8)
  })

  it('hides chips that already exist in the rates table', () => {
    render(<Wrapper initial={{ creative_director: 6000 }} />)
    expect(screen.queryByRole('button', { name: /\+ creative director/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+ designer/i })).toBeInTheDocument()
  })

  it('adds a row when a chip is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ designer/i }))
    expect(onChange).toHaveBeenCalledWith({ designer: 0 })
  })

  it('updates a rate when the user edits the rate input', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={{ designer: 0 }} onChange={onChange} />)
    const input = screen.getByLabelText(/rate for designer/i)
    await user.clear(input)
    await user.type(input, '4000')
    expect(onChange).toHaveBeenLastCalledWith({ designer: 4000 })
  })

  it('deletes a row when the delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={{ designer: 4000 }} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete designer/i }))
    expect(onChange).toHaveBeenCalledWith({})
  })

  it('adds a custom role with auto snake_cased key', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /add custom role/i }))
    const nameInput = screen.getByPlaceholderText(/role name/i)
    await user.type(nameInput, 'Motion Designer')
    await user.tab() // blur to commit
    expect(onChange).toHaveBeenCalledWith({ motion_designer: 0 })
  })
})
