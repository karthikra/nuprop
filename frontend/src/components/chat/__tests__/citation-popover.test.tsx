import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CitationPopover } from '../citation-popover'

describe('CitationPopover', () => {
  it('renders title, domain, cited snippet, and a source link', () => {
    render(
      <CitationPopover citation={{
        id: 1,
        url: 'https://reuters.com/business/pepsi-q4',
        title: 'Pepsi Q4 2024 earnings',
        domain: 'reuters.com',
        cited_text: 'Revenue grew 8.2% YoY to $91.4B...',
      }} />,
    )
    expect(screen.getByText('Pepsi Q4 2024 earnings')).toBeInTheDocument()
    expect(screen.getByText('reuters.com')).toBeInTheDocument()
    expect(screen.getByText(/Revenue grew 8.2%/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /open source/i })
    expect(link).toHaveAttribute('href', 'https://reuters.com/business/pepsi-q4')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
