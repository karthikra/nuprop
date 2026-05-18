import { useState } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Offering } from '../../../types/rate-card'
import { OfferingsStep } from '../offerings-step'

// jsdom doesn't implement window.confirm — stub it so deleteOffering proceeds.
beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const SAMPLE: Record<string, Offering> = {
  BI: {
    name: 'Brand Identity',
    code: 'BI',
    packages: {
      logo_design: { base: 150000, description: 'Logo + 2 variations', typical_hours: 40 },
    },
  },
}

/** Stateful wrapper so user-event keystrokes flow through React re-renders. */
function Wrapper({
  initial = {},
  onChange,
}: {
  initial?: Record<string, Offering>
  onChange?: (v: Record<string, Offering>) => void
}) {
  const [val, setVal] = useState<Record<string, Offering>>(initial)
  return (
    <OfferingsStep
      value={val}
      onChange={(next) => {
        setVal(next)
        onChange?.(next)
      }}
    />
  )
}

describe('OfferingsStep', () => {
  it('renders an empty state when no offerings exist', () => {
    render(<Wrapper />)
    expect(screen.getByRole('button', { name: /\+ add offering/i })).toBeInTheDocument()
    expect(screen.getByText(/pick or add an offering/i)).toBeInTheDocument()
  })

  it('appends a new offering with auto code O1 when Add offering is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ add offering/i }))
    expect(onChange).toHaveBeenCalledWith({
      O1: { name: 'New offering', code: 'O1', packages: {} },
    })
  })

  it('shows the selected offering in the left rail and packages in the right pane', () => {
    render(<Wrapper initial={SAMPLE} />)
    expect(screen.getByText(/BI · Brand Identity/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/offering name/i)).toHaveValue('Brand Identity')
    expect(screen.getByLabelText(/offering code/i)).toHaveValue('BI')
    expect(screen.getByDisplayValue('Logo Design')).toBeInTheDocument()
  })

  it('updates the offering name when the right-pane name input is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={SAMPLE} onChange={onChange} />)
    const nameInput = screen.getByLabelText(/offering name/i)
    await user.clear(nameInput)
    await user.type(nameInput, 'Brand Design')
    expect(onChange).toHaveBeenLastCalledWith({
      BI: { ...SAMPLE.BI, name: 'Brand Design' },
    })
  })

  it('re-keys the offering map when the code is edited', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={SAMPLE} onChange={onChange} />)
    const codeInput = screen.getByLabelText(/offering code/i)
    await user.clear(codeInput)
    await user.type(codeInput, 'BR')
    expect(onChange).toHaveBeenLastCalledWith({
      BR: { ...SAMPLE.BI, code: 'BR' },
    })
  })

  it('adds a package row when Add package is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /\+ add package/i }))
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      BI: expect.objectContaining({
        packages: expect.objectContaining({
          new_package: { base: 0, description: '', typical_hours: 0 },
        }),
      }),
    }))
  })

  it('deletes a package row when the package delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete logo design/i }))
    expect(onChange).toHaveBeenLastCalledWith({
      BI: { ...SAMPLE.BI, packages: {} },
    })
  })

  it('deletes the offering when the offering delete button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Wrapper initial={SAMPLE} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /delete offering brand identity/i }))
    expect(onChange).toHaveBeenLastCalledWith({})
  })

  it('refuses to re-key an offering when the target code is already taken', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const TWO_OFFERINGS = {
      ...SAMPLE,
      DM: { name: 'Digital Marketing', code: 'DM', packages: {} },
    }
    render(<Wrapper initial={TWO_OFFERINGS} onChange={onChange} />)

    // Brand Identity is selected by default. Try to rename its code to DM (taken).
    const codeInput = screen.getByLabelText(/offering code/i)
    await user.clear(codeInput)
    // user.type fires onChange per keystroke — typing "D" then "M"
    await user.type(codeInput, 'DM')

    // The collision guard should have prevented the rename when D + M was complete.
    // Check that DM still points at the original Digital Marketing, not Brand Identity.
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0]
    expect(lastCall?.DM?.name).toBe('Digital Marketing')
  })
})
