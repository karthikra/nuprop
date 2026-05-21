import { useState } from 'react'
import type { Candidate, DiscoveryResponse } from '../../../types/discovery'

interface Props {
  response: DiscoveryResponse
  onReview: (selected: Candidate[]) => void
  onSkipAll: () => void
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: 'short', year: 'numeric' })
}

export function CandidateList({ response, onReview, onSkipAll }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (domain: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(domain)) next.delete(domain)
      else next.add(domain)
      return next
    })

  const chosen = response.candidates.filter((c) => selected.has(c.domain))

  if (response.candidates.length === 0) {
    const exclusionNote =
      response.excluded_existing > 0
        ? ` (${response.excluded_existing} domains already linked to existing clients were excluded)`
        : ''
    return (
      <div className="space-y-3">
        <p className="text-sm text-stone-600">
          {`We scanned ${response.scanned_messages} messages and found no client-looking domains${exclusionNote}. Try a wider lookback, or add a client manually.`}
        </p>
        <div className="flex justify-end">
          <button onClick={onSkipAll} className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900">
            Close
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-stone-900">
          Found {response.candidates.length} candidate {response.candidates.length === 1 ? 'client' : 'clients'}
        </h2>
        {response.excluded_existing > 0 && (
          <p className="mt-1 text-xs text-stone-500">
            {response.excluded_existing} domains already linked to existing clients are excluded.
          </p>
        )}
      </div>

      <div className="max-h-96 overflow-y-auto space-y-1.5 border border-stone-200 rounded-lg p-1.5">
        {response.candidates.map((c) => {
          const isOn = selected.has(c.domain)
          return (
            <label
              key={c.domain}
              className={`flex items-start gap-3 p-2.5 rounded-md cursor-pointer ${
                isOn ? 'bg-stone-100' : 'hover:bg-stone-50'
              }`}
            >
              <input
                type="checkbox"
                aria-label={`Select ${c.suggested_name}`}
                checked={isOn}
                onChange={() => toggle(c.domain)}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-stone-900">{c.suggested_name}</span>
                  <span className="font-mono text-xs text-stone-400">{c.domain}</span>
                </div>
                <p className="text-xs text-stone-500 mt-0.5">
                  {c.message_count} emails · {c.sender_count} {c.sender_count === 1 ? 'sender' : 'senders'} ·{' '}
                  {formatDate(c.first_date)}–{formatDate(c.last_date)}
                </p>
              </div>
            </label>
          )
        })}
      </div>

      <div className="flex justify-between items-center pt-1">
        <button onClick={onSkipAll} className="text-sm text-stone-600 hover:text-stone-900">
          Skip all
        </button>
        <button
          onClick={() => onReview(chosen)}
          disabled={chosen.length === 0}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50 disabled:pointer-events-none"
        >
          Review {chosen.length} selected →
        </button>
      </div>
    </div>
  )
}
