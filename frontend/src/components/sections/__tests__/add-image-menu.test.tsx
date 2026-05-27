import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AddImageMenu } from '../add-image-menu'

const SAMPLE_FILE = new File(['fakebytes'], 'hero.png', { type: 'image/png' })

describe('AddImageMenu', () => {
  it('upload path: presign → PUT → commit', async () => {
    const user = userEvent.setup()
    const calls: { presign?: any; put?: any; commit?: any } = {}

    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/presign`,
        async ({ request }) => {
          calls.presign = await request.json()
          return HttpResponse.json({
            upload_url: 'https://s3.example/agency-1/p1/asset-1.png?upload=test',
            s3_key: 'agency-1/p1/asset-1.png',
            asset_id: 'asset-1',
          })
        },
      ),
      http.put('https://s3.example/agency-1/p1/asset-1.png', async ({ request }) => {
        calls.put = { method: request.method, contentType: request.headers.get('content-type') }
        return new HttpResponse(null, { status: 200 })
      }),
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/commit`,
        async ({ request }) => {
          calls.commit = await request.json()
          return HttpResponse.json({
            id: 'asset-1',
            kind: 'image',
            s3_key: 'agency-1/p1/asset-1.png',
            url: 'https://s3.example/agency-1/p1/asset-1.png?signed=ok',
            caption: null,
            ai_generated: false,
          })
        },
      ),
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    const fileInput = screen.getByLabelText(/upload file/i) as HTMLInputElement
    await user.upload(fileInput, SAMPLE_FILE)

    await waitFor(() => expect(calls.presign).toBeTruthy())
    expect(calls.presign).toEqual({
      kind: 'image',
      filename: 'hero.png',
      content_type: 'image/png',
      size: SAMPLE_FILE.size,
    })

    await waitFor(() => expect(calls.put?.contentType).toBe('image/png'))

    await waitFor(() => expect(calls.commit).toMatchObject({
      asset_id: 'asset-1',
      s3_key: 'agency-1/p1/asset-1.png',
      kind: 'image',
      content_type: 'image/png',
    }))
  })

  it('generate path: prompt → POST /generate', async () => {
    const user = userEvent.setup()
    let captured: any = null
    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/generate`,
        async ({ request }) => {
          captured = await request.json()
          return HttpResponse.json({
            id: 'ai-asset-1',
            kind: 'image',
            s3_key: 'agency-1/p1/ai-asset-1.png',
            url: 'https://s3.example/...?signed=ai',
            caption: null,
            ai_generated: true,
            prompt: 'an astronaut',
            provider: 'fal-ai/nano-banana',
          })
        },
      ),
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    await user.click(screen.getByRole('button', { name: /generate with ai/i }))
    const promptField = screen.getByLabelText(/image prompt/i)
    await user.type(promptField, 'an astronaut')
    await user.click(screen.getByRole('button', { name: /^generate$/i }))

    await waitFor(() => expect(captured).toEqual({ kind: 'image', prompt: 'an astronaut' }))
  })

  it('upload rejects an oversize file before calling presign', async () => {
    const user = userEvent.setup()
    let presigned = false
    server.use(
      http.post(
        `${API}/proposals/p1/sections/problem_statement/assets/presign`,
        () => {
          presigned = true
          return HttpResponse.json({})
        },
      ),
    )

    const big = new File(
      [new Uint8Array(11 * 1024 * 1024)],
      'big.png',
      { type: 'image/png' },
    )

    renderWithProviders(<AddImageMenu proposalId="p1" type="problem_statement" />)
    await user.click(screen.getByRole('button', { name: /add image/i }))
    const fileInput = screen.getByLabelText(/upload file/i) as HTMLInputElement
    await user.upload(fileInput, big)

    await screen.findByText(/exceeds 10 mb/i)
    expect(presigned).toBe(false)
  })
})
