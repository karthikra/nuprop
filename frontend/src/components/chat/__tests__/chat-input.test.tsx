import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from '../chat-input'

describe('ChatInput', () => {
  it('sends trimmed content on Enter and clears the textarea', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByPlaceholderText(/describe the client/i)
    await user.type(textarea, '  hello world  {Enter}')
    expect(onSend).toHaveBeenCalledWith('hello world')
    expect(textarea).toHaveValue('')
  })

  it('inserts a newline on Shift+Enter instead of sending', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByPlaceholderText(/describe the client/i)
    await user.type(textarea, 'line one{Shift>}{Enter}{/Shift}line two')
    expect(onSend).not.toHaveBeenCalled()
    expect(textarea).toHaveValue('line one\nline two')
  })

  it('does not send whitespace-only content', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await user.type(screen.getByPlaceholderText(/describe the client/i), '   {Enter}')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('sends when the send button is clicked', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await user.type(screen.getByPlaceholderText(/describe the client/i), 'via button')
    await user.click(screen.getByRole('button'))
    expect(onSend).toHaveBeenCalledWith('via button')
  })

  it('disables the textarea and button when disabled', () => {
    render(<ChatInput onSend={vi.fn()} disabled />)
    expect(screen.getByPlaceholderText(/describe the client/i)).toBeDisabled()
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
