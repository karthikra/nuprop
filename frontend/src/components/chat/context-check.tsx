import { useState } from 'react'
import { api } from '../../api/client'

interface Props {
  clientId: string
  clientName: string
  hasContext: boolean
  onComplete: () => void
}

export function ContextCheck({ clientId, clientName, hasContext, onComplete }: Props) {
  const [mode, setMode] = useState<'prompt' | 'paste' | 'loading' | 'done'>(hasContext ? 'done' : 'prompt')
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async () => {
    if (!text.trim()) return
    setSaving(true)
    try {
      await api.post(`/clients/${clientId}/context`, { raw_text: text })
      setMode('done')
      onComplete()
    } catch (err) {
      console.error('Context extraction failed:', err)
    }
    setSaving(false)
  }

  if (mode === 'done' || hasContext) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[80%] rounded-2xl bg-white border border-stone-200 px-5 py-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <span className="text-sm font-medium text-stone-900">Client context loaded for {clientName}</span>
          </div>
          <p className="text-sm text-stone-500">Past interactions and intelligence will shape this proposal.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl bg-indigo-50 border border-indigo-200 px-5 py-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-indigo-900">Do you have history with {clientName}?</span>
        </div>

        {mode === 'prompt' && (
          <>
            <p className="text-sm text-indigo-700 mb-3">
              Sharing past interactions helps write a better proposal. You can:
            </p>
            <div className="space-y-2">
              <button
                onClick={() => setMode('paste')}
                className="w-full text-left rounded-lg border border-indigo-200 bg-white px-4 py-3 text-sm hover:bg-indigo-50 transition-colors"
              >
                <span className="font-medium text-stone-900">Paste emails, notes, or meeting summaries</span>
                <p className="text-xs text-stone-500 mt-0.5">I'll extract contacts, pricing signals, and relationship details</p>
              </button>
              <button
                onClick={onComplete}
                className="w-full text-left rounded-lg border border-indigo-200 bg-white px-4 py-3 text-sm hover:bg-indigo-50 transition-colors"
              >
                <span className="font-medium text-stone-900">Cold pitch — no prior history</span>
                <p className="text-xs text-stone-500 mt-0.5">I'll rely on web research only</p>
              </button>
            </div>
          </>
        )}

        {mode === 'paste' && (
          <>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"Paste email threads, meeting notes, past proposal feedback, budget discussions...\n\nExample:\n\"We did a poster project for them in August for ₹2.4L. They loved the speed but complained about revision delays. Priya from IC is the main contact. Budget for this might be tight — she mentioned constraints this quarter.\""}
              rows={8}
              className="w-full rounded-lg border border-indigo-200 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-3"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={handleSubmit}
                disabled={saving || !text.trim()}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
              >
                {saving ? 'Extracting...' : 'Extract Context'}
              </button>
              <button
                onClick={onComplete}
                className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
              >
                Skip
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
