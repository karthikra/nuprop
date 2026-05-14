import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ClientListPage } from '../list'

const client1 = {
  id: 'c1', name: 'Northwind', slug: 'northwind', industry: 'logistics', size: 'sme',
  contacts: [], notes: null, tags: ['vip'], context_profile: {}, created_at: '', updated_at: '',
}

describe('ClientListPage', () => {
  it('shows the empty state when there are no clients', async () => {
    server.use(http.get(`${API}/clients`, () => HttpResponse.json([])))
    renderWithProviders(<ClientListPage />)
    expect(await screen.findByText(/no clients yet/i)).toBeInTheDocument()
  })

  it('lists the clients returned by the API', async () => {
    server.use(http.get(`${API}/clients`, () => HttpResponse.json([client1])))
    renderWithProviders(<ClientListPage />)
    expect(await screen.findByText('Northwind')).toBeInTheDocument()
    expect(screen.getByText('logistics')).toBeInTheDocument()
  })

  it('passes the search box value to the clients query', async () => {
    const user = userEvent.setup()
    const seen: string[] = []
    server.use(
      http.get(`${API}/clients`, ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('q') || '')
        return HttpResponse.json([])
      }),
    )
    renderWithProviders(<ClientListPage />)
    await screen.findByText(/no clients yet/i)

    await user.type(screen.getByPlaceholderText(/search clients/i), 'north')
    await waitFor(() => expect(seen).toContain('north'))
  })

  it('opens the create form and posts a new client', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get(`${API}/clients`, () => HttpResponse.json([])),
      http.post(`${API}/clients`, async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(client1)
      }),
    )
    renderWithProviders(<ClientListPage />)
    await screen.findByText(/no clients yet/i)

    await user.click(screen.getByRole('button', { name: /add client/i }))
    const modal = screen.getByText('New client').closest('div') as HTMLElement
    await user.type(within(modal).getAllByRole('textbox')[0], 'Globex')
    await user.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => expect(posted).toEqual({ name: 'Globex', tags: [] }))
  })
})
