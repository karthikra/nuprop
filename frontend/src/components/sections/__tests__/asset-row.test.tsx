import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AssetRow } from '../asset-row'
import type { SectionAsset } from '../../../types/proposal'

const ASSETS: SectionAsset[] = [
  {
    id: 'a1',
    kind: 'image',
    s3_key: 'agency-1/p1/a1.png',
    url: 'https://s3.example/agency-1/p1/a1.png?signed=test',
    caption: 'hero shot',
    ai_generated: false,
  },
  {
    id: 'a2',
    kind: 'image',
    s3_key: 'agency-1/p1/a2.png',
    url: 'https://s3.example/agency-1/p1/a2.png?signed=test',
    caption: null,
    ai_generated: true,
    prompt: 'an astronaut',
    provider: 'fal-ai/nano-banana',
  },
]

describe('AssetRow', () => {
  it('renders one thumbnail per asset', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0]).toHaveAttribute('src', ASSETS[0].url)
    expect(imgs[1]).toHaveAttribute('src', ASSETS[1].url)
  })

  it('shows captions when present', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    expect(screen.getByText('hero shot')).toBeInTheDocument()
  })

  it('marks AI-generated assets', () => {
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    expect(screen.getAllByText(/AI/i).length).toBeGreaterThan(0)
  })

  it('renders nothing for an empty assets array', () => {
    const { container } = renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={[]} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('clicking delete sends the DELETE request', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.delete(`${API}/proposals/p1/sections/problem_statement/assets/a1`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderWithProviders(
      <AssetRow proposalId="p1" type="problem_statement" assets={ASSETS} />,
    )
    await user.click(screen.getAllByRole('button', { name: /delete asset/i })[0])
    await waitFor(() => expect(deleted).toBe(true))
  })
})
