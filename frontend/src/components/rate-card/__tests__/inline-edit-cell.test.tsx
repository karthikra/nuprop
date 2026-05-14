import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InlineEditCell } from '../inline-edit-cell'

describe('InlineEditCell', () => {
  it('renders a currency-formatted display value', () => {
    render(<InlineEditCell value={150000} format="currency" onSave={vi.fn()} />)
    expect(screen.getByText('₹1,50,000')).toBeInTheDocument()
  })

  it('renders a percent value as a whole percentage', () => {
    render(<InlineEditCell value={0.1} format="percent" onSave={vi.fn()} />)
    expect(screen.getByText('10%')).toBeInTheDocument()
  })

  it('enters edit mode on click and shows an input', async () => {
    const user = userEvent.setup()
    render(<InlineEditCell value={100} format="number" onSave={vi.fn()} />)
    await user.click(screen.getByText('100'))
    expect(screen.getByRole('spinbutton')).toBeInTheDocument()
  })

  it('saves a new numeric value on Enter', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<InlineEditCell value={100} format="number" onSave={onSave} />)
    await user.click(screen.getByText('100'))
    const input = screen.getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '250{Enter}')
    expect(onSave).toHaveBeenCalledWith(250)
  })

  it('converts a percent input back to a fraction on save', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<InlineEditCell value={0.1} format="percent" onSave={onSave} />)
    await user.click(screen.getByText('10%'))
    const input = screen.getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '25{Enter}')
    expect(onSave).toHaveBeenCalledWith(0.25)
  })

  it('does not call onSave when the value is unchanged', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<InlineEditCell value={100} format="number" onSave={onSave} />)
    await user.click(screen.getByText('100'))
    await user.type(screen.getByRole('spinbutton'), '{Enter}') // submit without editing
    expect(onSave).not.toHaveBeenCalled()
  })

  it('discards edit mode on Escape', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<InlineEditCell value={100} format="number" onSave={onSave} />)
    await user.click(screen.getByText('100'))
    expect(screen.getByRole('spinbutton')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('saves a text value on blur', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<InlineEditCell value="hello" format="text" onSave={onSave} />)
    await user.click(screen.getByText('hello'))
    const input = screen.getByRole('textbox')
    await user.clear(input)
    await user.type(input, 'world')
    await user.tab() // blur
    expect(onSave).toHaveBeenCalledWith('world')
  })
})
