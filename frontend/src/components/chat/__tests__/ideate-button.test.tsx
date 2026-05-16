import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IdeateButton } from '../ideate-button'

describe('IdeateButton', () => {
  beforeEach(() => {
    window.location.hash = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('clicks toggle the parent open prop and update the URL hash to #ideate', async () => {
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    let open = false
    const setOpen = (v: boolean) => { open = v }
    const { rerender } = render(<IdeateButton open={open} onToggle={setOpen} />)

    await userEvent.click(screen.getByRole('button', { name: /ideate/i }))
    expect(open).toBe(true)

    // Parent re-renders with new open state, triggering the sync effect
    rerender(<IdeateButton open={true} onToggle={setOpen} />)
    expect(replaceStateSpy).toHaveBeenCalledWith(null, '', expect.stringContaining('#ideate'))

    replaceStateSpy.mockClear()

    await userEvent.click(screen.getByRole('button', { name: /ideate/i }))
    expect(open).toBe(false)

    // Parent re-renders with new open state
    rerender(<IdeateButton open={false} onToggle={setOpen} />)
    expect(replaceStateSpy).toHaveBeenCalledWith(null, '', expect.not.stringContaining('#ideate'))
  })

  it('honors a preexisting #ideate hash on mount', () => {
    window.history.replaceState(null, '', '#ideate')
    let open = false
    const setOpen = (v: boolean) => { open = v }
    render(<IdeateButton open={open} onToggle={setOpen} />)
    expect(open).toBe(true)
  })
})
