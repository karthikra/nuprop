import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClientForm } from '../client-form'
import type { Client } from '../../../types/client'

const existingClient: Client = {
  id: 'c1', name: 'Existing Co', slug: 'existing-co', industry: 'retail', size: 'sme',
  contacts: [], notes: 'some notes', tags: ['a', 'b'], context_profile: {},
  created_at: '', updated_at: '',
}

describe('ClientForm', () => {
  it('submits the name and comma-split, trimmed tags', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ClientForm onSubmit={onSubmit} onCancel={vi.fn()} saving={false} />)

    await user.type(screen.getAllByRole('textbox')[0], 'Globex')
    await user.type(screen.getByPlaceholderText(/comma-separated/i), 'vip, tech ,  ')
    await user.click(screen.getByRole('button', { name: /create/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Globex',
      industry: undefined,
      size: undefined,
      notes: undefined,
      tags: ['vip', 'tech'],
    })
  })

  it('hydrates its fields from the initial client', () => {
    render(<ClientForm initial={existingClient} onSubmit={vi.fn()} onCancel={vi.fn()} saving={false} />)
    expect(screen.getAllByRole('textbox')[0]).toHaveValue('Existing Co')
    expect(screen.getByPlaceholderText(/Telecom/i)).toHaveValue('retail')
    expect(screen.getByPlaceholderText(/comma-separated/i)).toHaveValue('a, b')
    expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument()
  })

  it('disables the submit button while saving', () => {
    render(<ClientForm onSubmit={vi.fn()} onCancel={vi.fn()} saving={true} />)
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
  })

  it('disables the submit button when the name is empty', () => {
    render(<ClientForm onSubmit={vi.fn()} onCancel={vi.fn()} saving={false} />)
    expect(screen.getByRole('button', { name: /create/i })).toBeDisabled()
  })

  it('calls onCancel when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ClientForm onSubmit={vi.fn()} onCancel={onCancel} saving={false} />)
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})
