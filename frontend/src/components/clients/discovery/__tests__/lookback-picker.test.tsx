import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LookbackPicker } from '../lookback-picker'

describe('LookbackPicker', () => {
  it('renders three buttons (30, 90, 365 days)', () => {
    render(<LookbackPicker onPick={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByRole('button', { name: /30 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /90 days/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /365 days/i })).toBeInTheDocument()
  })

  it('calls onPick with the chosen number when a button is clicked', async () => {
    const user = userEvent.setup()
    const onPick = vi.fn()
    render(<LookbackPicker onPick={onPick} onCancel={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /90 days/i }))
    expect(onPick).toHaveBeenCalledWith(90)
  })

  it('calls onCancel when the cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<LookbackPicker onPick={vi.fn()} onCancel={onCancel} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
