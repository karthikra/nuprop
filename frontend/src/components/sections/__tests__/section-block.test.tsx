import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SectionBlock } from '../section-block'

const SAMPLE = {
  content: 'Original content.',
  assets: [],
  included: true,
  metadata: {},
}

describe('SectionBlock', () => {
  it('renders the section title and current content', () => {
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    expect(screen.getByText('Problem statement')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Original content.')).toBeInTheDocument()
  })

  it('auto-saves edited content after the debounce', async () => {
    const user = userEvent.setup()
    let lastBody: any = null
    server.use(
      http.patch(`${API}/proposals/p1/sections/problem_statement`, async ({ request }) => {
        lastBody = await request.json()
        return HttpResponse.json({ ...SAMPLE, content: lastBody.content })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    const editor = screen.getByRole('textbox', { name: /problem statement/i })
    await user.click(editor)
    await user.keyboard(' Added text.')
    await waitFor(
      () => expect(lastBody?.content).toMatch(/Added text\./),
      { timeout: 2000 },
    )
  })

  it('regenerate button posts to the regenerate endpoint and updates the block', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/proposals/p1/sections/problem_statement/regenerate`, () =>
        HttpResponse.json({ ...SAMPLE, content: 'Fresh content.' }),
      ),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /regenerate/i }))
    await waitFor(() => expect(screen.getByDisplayValue('Fresh content.')).toBeInTheDocument())
  })

  it('refine flow opens a prompt field, submits the instructions, and replaces content', async () => {
    const user = userEvent.setup()
    let lastBody: any = null
    server.use(
      http.post(`${API}/proposals/p1/sections/problem_statement/refine`, async ({ request }) => {
        lastBody = await request.json()
        return HttpResponse.json({ ...SAMPLE, content: 'Shorter content.' })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /refine/i }))
    const prompt = screen.getByLabelText(/refinement instructions/i)
    await user.type(prompt, 'Make it shorter')
    await user.click(screen.getByRole('button', { name: /apply refinement/i }))
    await waitFor(() => expect(lastBody).toEqual({ instructions: 'Make it shorter' }))
    await waitFor(() => expect(screen.getByDisplayValue('Shorter content.')).toBeInTheDocument())
  })

  it('toggle-off greys out the block and shows a re-include action', async () => {
    const user = userEvent.setup()
    server.use(
      http.patch(`${API}/proposals/p1/sections/problem_statement`, async ({ request }) => {
        const body = await request.json() as { included?: boolean }
        return HttpResponse.json({ ...SAMPLE, included: body.included ?? true })
      }),
    )
    renderWithProviders(
      <SectionBlock proposalId="p1" type="problem_statement" title="Problem statement" section={SAMPLE} />,
    )
    await user.click(screen.getByRole('button', { name: /exclude this section/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /re-include/i })).toBeInTheDocument())
  })
})
