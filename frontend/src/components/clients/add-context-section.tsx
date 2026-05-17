import { useState } from 'react'
import { useContextPreview, useContextSave, type ContextPreview } from '../../api/clients'
import { formatApiError } from '../../api/client'

interface AddContextSectionProps {
  clientId: string
}

type Mode = 'collapsed' | 'editing' | 'preview'

export function AddContextSection({ clientId }: AddContextSectionProps) {
  const [mode, setMode] = useState<Mode>('collapsed')
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const previewMut = useContextPreview(clientId)
  const saveMut = useContextSave(clientId)

  const handleExtract = async () => {
    if (!text.trim()) return
    previewMut.mutate(text, {
      onSuccess: (data) => {
        setPreview(data)
        setMode('preview')
      },
    })
  }

  const handleSave = () => {
    if (!preview) return
    saveMut.mutate(preview.extracted, {
      onSuccess: () => {
        // Collapse back to the closed state and clear inputs
        setMode('collapsed')
        setText('')
        setPreview(null)
      },
    })
  }

  const handleEditText = () => {
    setMode('editing')
    setPreview(null)
  }

  const handleCancel = () => {
    setMode('collapsed')
    setText('')
    setPreview(null)
    previewMut.reset()
    saveMut.reset()
  }

  if (mode === 'collapsed') {
    return (
      <div className="md:col-span-2">
        <button
          type="button"
          onClick={() => setMode('editing')}
          className="w-full rounded-xl border border-dashed border-indigo-300 bg-indigo-50 hover:bg-indigo-100 px-5 py-3 text-left text-sm text-indigo-700 font-medium transition-colors"
        >
          ✨ Add or update context
          <span className="block text-xs text-indigo-500 mt-0.5">Paste emails, notes, or meeting summaries — I'll extract relationship, pricing signals, and past work.</span>
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide">Add Context</h3>

      {mode === 'editing' ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={'Paste email threads, meeting notes, past proposal feedback, budget discussions...\n\nExample:\n"We did a poster project for them in August for ₹2.4L. Priya from IC is the main contact. Budget for this might be tight."'}
            rows={8}
            className="mt-3 w-full rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
            autoFocus
          />
          {previewMut.isError ? (
            <p className="mt-2 text-sm text-red-600">{formatApiError(previewMut.error, 'Extraction failed')}</p>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleExtract}
              disabled={previewMut.isPending || !text.trim()}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {previewMut.isPending ? 'Extracting...' : 'Extract preview'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Cancel
            </button>
          </div>
        </>
      ) : null}

      {mode === 'preview' && preview != null ? (
        <>
          <p className="mt-3 text-sm text-indigo-700">Here's what the AI extracted. Review and save, or edit your text and try again.</p>
          <ExtractedPreview profile={preview.extracted} />
          {saveMut.isError ? (
            <p className="mt-2 text-sm text-red-600">{formatApiError(saveMut.error, 'Save failed')}</p>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saveMut.isPending}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {saveMut.isPending ? 'Saving...' : 'Save to client'}
            </button>
            <button
              type="button"
              onClick={handleEditText}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Edit text
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Cancel
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}

/** Inline render of the extracted preview — visually parallels ContextProfileCard
 *  so the user can compare before and after. Kept here (not extracted) because it's
 *  only used in this file. */
function ExtractedPreview({ profile }: { profile: Record<string, unknown> }) {
  const rel = profile.relationship as Record<string, unknown> | undefined
  const pricing = profile.pricing_intelligence as Record<string, unknown> | undefined
  const pastWork = Array.isArray(profile.past_work) ? profile.past_work as Array<Record<string, unknown>> : []
  const risks = Array.isArray(profile.risks) ? profile.risks as Array<Record<string, unknown>> : []
  const opportunities = Array.isArray(profile.opportunities) ? profile.opportunities as Array<Record<string, unknown>> : []

  const isEmpty = !rel?.status && !pricing?.price_sensitivity && pastWork.length === 0 && risks.length === 0 && opportunities.length === 0
  if (isEmpty) {
    return <p className="mt-3 text-sm text-stone-500 italic">The AI didn't find any structured signals in that text. Try pasting something more specific (emails, meeting notes, past project details).</p>
  }

  return (
    <div className="mt-3 rounded-lg border border-indigo-100 bg-white p-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
      {rel?.status != null ? (
        <div>
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Relationship</p>
          <p className="text-stone-800 capitalize">{String(rel.status)}</p>
          {(rel.primary_contact as Record<string, unknown> | undefined)?.name != null ? (
            <p className="text-stone-500 text-xs">Contact: {String((rel.primary_contact as Record<string, unknown>).name)}</p>
          ) : null}
        </div>
      ) : null}
      {pricing?.price_sensitivity != null ? (
        <div>
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Price Sensitivity</p>
          <p className="text-stone-800 capitalize">{String(pricing.price_sensitivity)}</p>
        </div>
      ) : null}
      {pastWork.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Past Work</p>
          {pastWork.map((w, i) => (
            <p key={i} className="text-stone-700">
              <span className="font-medium">{String(w.project || '')}</span>
              {w.value != null ? <span className="text-stone-500"> — ₹{Number(w.value).toLocaleString()}</span> : null}
            </p>
          ))}
        </div>
      ) : null}
      {risks.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Risks</p>
          {risks.map((r, i) => (
            <p key={i} className="text-stone-700 text-xs">⚠ {String(r.signal || '')}</p>
          ))}
        </div>
      ) : null}
      {opportunities.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Opportunities</p>
          {opportunities.map((o, i) => (
            <p key={i} className="text-stone-700 text-xs">✨ {String(o.signal || '')}</p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
