import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClientForm } from '../client-form'
import type { Client, ClientCreate, ContactInfo } from '../../../types/client'

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

function Wrapper({
  initialContacts,
  onSubmit,
}: {
  initialContacts?: ContactInfo[]
  onSubmit?: (data: ClientCreate) => void
}) {
  return (
    <ClientForm
      onSubmit={onSubmit ?? (() => {})}
      onCancel={() => {}}
      saving={false}
      initialContacts={initialContacts}
    />
  )
}

describe('ClientForm contacts editor', () => {
  it('pre-fills contacts from initialContacts', () => {
    render(<Wrapper initialContacts={[
      { name: 'Jane', email: 'jane@acme.com' },
      { name: 'Bob', email: 'bob@acme.com' },
    ]} />)
    expect(screen.getByDisplayValue('Jane')).toBeInTheDocument()
    expect(screen.getByDisplayValue('jane@acme.com')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Bob')).toBeInTheDocument()
  })

  it('includes contacts in the submit payload', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper
      initialContacts={[{ name: 'Jane', email: 'jane@acme.com' }]}
      onSubmit={onSubmit}
    />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Acme',
      contacts: [{ name: 'Jane', email: 'jane@acme.com' }],
    }))
  })

  it('lets the user add a new contact row', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    await user.click(screen.getByRole('button', { name: /add contact/i }))
    const nameInputs = screen.getAllByPlaceholderText(/contact name/i)
    const emailInputs = screen.getAllByPlaceholderText(/contact email/i)
    await user.type(nameInputs[0], 'Carol')
    await user.type(emailInputs[0], 'carol@acme.com')
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      contacts: [{ name: 'Carol', email: 'carol@acme.com' }],
    }))
  })

  it('lets the user remove a contact row', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Wrapper
      initialContacts={[
        { name: 'Jane', email: 'jane@acme.com' },
        { name: 'Bob', email: 'bob@acme.com' },
      ]}
      onSubmit={onSubmit}
    />)
    await user.type(screen.getByLabelText(/client name/i), 'Acme')
    const removeButtons = screen.getAllByRole('button', { name: /remove contact/i })
    await user.click(removeButtons[1])
    await user.click(screen.getByRole('button', { name: /save|create/i }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      contacts: [{ name: 'Jane', email: 'jane@acme.com' }],
    }))
  })
})
