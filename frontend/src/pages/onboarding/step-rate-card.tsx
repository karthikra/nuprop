import { useState } from 'react'

interface Props {
  onSubmit: (data: Record<string, unknown>) => void
  saving: boolean
}

const PLACEHOLDER = `{
  "version": "2026-Q2",
  "offerings": {
    "brand_identity": {
      "packages": {
        "logo_design": { "base": 150000, "description": "Logo design" }
      }
    }
  },
  "hourly_rates": {
    "creative_director": 6000,
    "senior_designer": 4000
  },
  "multipliers": {
    "urgency_rush": 1.5,
    "complexity_enterprise": 1.5,
    "annual_bundle": 0.88
  }
}`

export function StepRateCard({ onSubmit, saving }: Props) {
  const [mode, setMode] = useState<'paste' | 'skip'>('paste')
  const [json, setJson] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = () => {
    if (mode === 'skip') {
      onSubmit({ version: 'v1', offerings: {}, hourly_rates: {}, multipliers: {} })
      return
    }
    try {
      const parsed = JSON.parse(json)
      onSubmit({
        version: parsed.version || 'v1',
        offerings: parsed.offerings || {},
        hourly_rates: parsed.hourly_rates || {},
        multipliers: parsed.multipliers || {},
        pass_through_markup: parsed.pass_through_markup || 0.10,
        standard_options: parsed.standard_options || 3,
        standard_revisions: parsed.standard_revisions || 2,
      })
    } catch {
      setError('Invalid JSON. Please check your rate card format.')
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-stone-600">
        Paste your rate card as JSON, or skip and set it up later.
      </p>

      <div className="flex gap-2">
        <button
          onClick={() => setMode('paste')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
            mode === 'paste' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-600'
          }`}
        >
          Paste JSON
        </button>
        <button
          onClick={() => setMode('skip')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
            mode === 'skip' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-600'
          }`}
        >
          Skip for now
        </button>
      </div>

      {mode === 'paste' && (
        <>
          <textarea
            value={json}
            onChange={(e) => { setJson(e.target.value); setError('') }}
            placeholder={PLACEHOLDER}
            rows={14}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-900"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
        </>
      )}

      {mode === 'skip' && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          You can set up your rate card later in Settings. The proposal builder will ask you for pricing manually.
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={saving || (mode === 'paste' && !json)}
        className="w-full rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
      >
        {saving ? 'Saving...' : mode === 'skip' ? 'Skip & Continue' : 'Save & Continue'}
      </button>
    </div>
  )
}
