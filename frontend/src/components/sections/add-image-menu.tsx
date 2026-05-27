import axios from 'axios'
import { useRef, useState } from 'react'
import {
  useCommitAsset,
  useGenerateAsset,
  usePresignAsset,
} from '../../api/proposals'
import type { SectionType } from '../../types/proposal'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024 // 10 MB — backend will also reject

interface Props {
  proposalId: string
  type: SectionType
}

export function AddImageMenu({ proposalId, type }: Props) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'idle' | 'generate'>('idle')
  const [prompt, setPrompt] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const presign = usePresignAsset(proposalId)
  const commit = useCommitAsset(proposalId)
  const generate = useGenerateAsset(proposalId)

  const reset = () => {
    setOpen(false)
    setMode('idle')
    setPrompt('')
    setError(null)
  }

  const onPickFile = () => fileRef.current?.click()

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setError(null)

    if (f.size > MAX_IMAGE_BYTES) {
      setError('File exceeds 10 MB.')
      e.target.value = ''
      return
    }

    try {
      const presigned = await presign.mutateAsync({
        type,
        kind: 'image',
        filename: f.name,
        content_type: f.type || 'image/png',
        size: f.size,
      })

      // Upload directly to S3 — bypass our backend.
      await axios.put(presigned.upload_url, f, {
        headers: { 'Content-Type': f.type || 'image/png' },
      })

      // Read dimensions before commit so the editor can use them.
      const dims = await readImageDimensions(f).catch(() => ({ width: null, height: null }))

      await commit.mutateAsync({
        type,
        asset_id: presigned.asset_id,
        s3_key: presigned.s3_key,
        kind: 'image',
        content_type: f.type || 'image/png',
        caption: null,
        width: dims.width,
        height: dims.height,
      })

      reset()
    } catch (err) {
      setError('Upload failed. Try again.')
      // eslint-disable-next-line no-console
      console.error(err)
    } finally {
      if (e.target) e.target.value = ''
    }
  }

  const onGenerate = async () => {
    if (!prompt.trim()) return
    setError(null)
    try {
      await generate.mutateAsync({ type, kind: 'image', prompt: prompt.trim() })
      reset()
    } catch (err) {
      setError('Generation failed. Try again.')
      // eslint-disable-next-line no-console
      console.error(err)
    }
  }

  return (
    <div className="relative mt-3 inline-block">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        className="rounded-md border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50"
      >
        + Add image
      </button>

      {open && mode === 'idle' && (
        <div className="absolute left-0 z-10 mt-1 w-52 rounded-md border border-stone-200 bg-white p-1 shadow-lg">
          <label
            htmlFor={`upload-${type}`}
            className="block cursor-pointer rounded px-3 py-2 text-xs text-stone-700 hover:bg-stone-100"
            onClick={onPickFile}
          >
            Upload file
          </label>
          <input
            id={`upload-${type}`}
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="sr-only"
            onChange={onFileChange}
          />
          <button
            type="button"
            onClick={() => setMode('generate')}
            className="block w-full rounded px-3 py-2 text-left text-xs text-stone-700 hover:bg-stone-100"
          >
            Generate with AI
          </button>
        </div>
      )}

      {open && mode === 'generate' && (
        <div className="absolute left-0 z-10 mt-1 w-72 rounded-md border border-stone-200 bg-white p-3 shadow-lg">
          <label htmlFor={`prompt-${type}`} className="block text-xs font-medium text-stone-700">
            Image prompt
          </label>
          <textarea
            id={`prompt-${type}`}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded border border-stone-200 p-2 text-xs"
          />
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={reset}
              className="rounded px-2 py-1 text-xs text-stone-600 hover:bg-stone-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onGenerate}
              disabled={generate.isPending || !prompt.trim()}
              className="rounded bg-stone-900 px-3 py-1 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {generate.isPending ? 'Generating…' : 'Generate'}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-1 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

function readImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    let settled = false
    const done = (fn: () => void) => {
      if (settled) return
      settled = true
      fn()
    }
    img.onload = () =>
      done(() => resolve({ width: img.naturalWidth, height: img.naturalHeight }))
    img.onerror = () => done(() => reject(new Error('image load failed')))
    // Fallback: jsdom / test environments may never fire Image events.
    // Don't block the upload flow waiting for dimensions.
    setTimeout(() => done(() => reject(new Error('image load timeout'))), 250)
    img.src = URL.createObjectURL(file)
  })
}
