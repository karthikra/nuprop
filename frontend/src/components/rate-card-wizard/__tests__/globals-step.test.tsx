import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GlobalsStep } from '../globals-step'

const DEFAULTS = { pass_through_markup: 0.10, standard_options: 3, standard_revisions: 2 }

describe('GlobalsStep', () => {
  it('renders all three fields with their default values', () => {
    render(<GlobalsStep value={DEFAULTS} onChange={vi.fn()} />)
    expect(screen.getByLabelText(/pass-through markup/i)).toHaveValue(10)
    expect(screen.getByLabelText(/standard options/i)).toHaveValue(3)
    expect(screen.getByLabelText(/standard revision rounds/i)).toHaveValue(2)
  })

  it('calls onChange with the new pass-through markup as a decimal', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/pass-through markup/i)
    await user.clear(input)
    await user.type(input, '15')
    // The last call should reflect 15% = 0.15
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, pass_through_markup: 0.15 })
  })

  it('calls onChange when standard options is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/standard options/i)
    await user.clear(input)
    await user.type(input, '5')
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, standard_options: 5 })
  })

  it('calls onChange when standard revisions is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<GlobalsStep value={DEFAULTS} onChange={onChange} />)
    const input = screen.getByLabelText(/standard revision rounds/i)
    await user.clear(input)
    await user.type(input, '4')
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULTS, standard_revisions: 4 })
  })
})
