import { useState } from 'react'
import {
  useFillRateCardGaps,
  useSkipRateCardGaps,
  useImportRateCardXlsx,
  useConfirmRateCardImport,
} from '../../api/proposals'

interface Gaps {
  missing_roles: string[]
  missing_offerings: string[]
  needed_roles: string[]
  needed_offerings: string[]
}

interface PreviewShape {
  hourly_rates: Record<string, number>
  offerings: Record<string, { name: string; base_price: number }>
  multipliers?: Record<string, number>
  low_confidence_fields?: string[]
}

interface Props {
  proposalId: string
  gaps: Gaps
}

function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function RateGapCard({ proposalId, gaps }: Props) {
  const fill = useFillRateCardGaps(proposalId)
  const skip = useSkipRateCardGaps(proposalId)
  const imp = useImportRateCardXlsx(proposalId)
  const confirm = useConfirmRateCardImport(proposalId)

  const [rateValues, setRateValues] = useState<Record<string, string>>({})
  const [offeringValues, setOfferingValues] = useState<
    Record<string, { name: string; base_price: string }>
  >(() =>
    Object.fromEntries(
      gaps.missing_offerings.map(k => [k, { name: humanize(k), base_price: '' }]),
    ),
  )
  const [preview, setPreview] = useState<PreviewShape | null>(null)

  const manualFillValid = (
    gaps.missing_roles.every(k => {
      const v = parseInt(rateValues[k] ?? '', 10)
      return Number.isFinite(v) && v > 0
    }) &&
    gaps.missing_offerings.every(k => {
      const v = parseInt(offeringValues[k]?.base_price ?? '', 10)
      return Number.isFinite(v) && v > 0
    })
  )

  const onSubmitManual = () => {
    const hourly_rates: Record<string, number> = {}
    for (const k of gaps.missing_roles) {
      const v = parseInt(rateValues[k] ?? '', 10)
      if (!Number.isNaN(v)) hourly_rates[k] = v
    }
    const offerings: Record<string, { name: string; base_price: number }> = {}
    for (const k of gaps.missing_offerings) {
      const o = offeringValues[k]
      const v = parseInt(o.base_price, 10)
      if (!Number.isNaN(v)) {
        offerings[k] = { name: o.name || humanize(k), base_price: v }
      }
    }
    fill.mutate({ hourly_rates, offerings })
  }

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await imp.mutateAsync(file)
      if (result) setPreview(result)
    } catch {
      // React Query captures the error in imp.isError; we render it below.
    }
  }

  const onConfirmPreview = () => {
    if (!preview) return
    confirm.mutate(preview, {
      onSuccess: () => setPreview(null),
    })
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 space-y-4">
      <p className="text-sm text-stone-700">
        I need a few rates to price this proposal. Drop in your rate-card spreadsheet,
        fill the fields manually, or skip to use estimated defaults.
      </p>

      {preview ? (
        <div className="rounded-lg bg-white border border-stone-200 p-3 space-y-2">
          <h4 className="text-sm font-medium text-stone-900">Parsed preview</h4>
          <pre className="text-xs text-stone-700 whitespace-pre-wrap">
            {JSON.stringify(preview, null, 2)}
          </pre>
          <div className="flex gap-2">
            <button
              onClick={onConfirmPreview}
              disabled={confirm.isPending}
              className="rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {confirm.isPending ? 'Confirming…' : 'Confirm and continue'}
            </button>
            <button
              onClick={() => setPreview(null)}
              className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <label className="block">
            <span className="text-xs text-stone-600">Upload rate card spreadsheet (.xlsx)</span>
            <input
              type="file"
              accept=".xlsx"
              aria-label="Upload rate card spreadsheet"
              onChange={onFileChange}
              className="mt-1 block w-full text-sm"
            />
          </label>

          {imp.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-2 text-xs text-red-700">
              Upload failed — please check the file is a valid .xlsx and under 5 MB.
            </div>
          ) : null}

          <div className="border-t border-amber-200 pt-3 space-y-2">
            <p className="text-xs text-stone-600">Or fill manually:</p>
            {gaps.missing_roles.map(role => (
              <div key={role} className="flex items-center gap-2">
                <label className="text-xs text-stone-700 w-44" htmlFor={`role-${role}`}>
                  {humanize(role)}
                </label>
                <input
                  id={`role-${role}`}
                  aria-label={humanize(role)}
                  type="number"
                  value={rateValues[role] ?? ''}
                  onChange={e => setRateValues(s => ({ ...s, [role]: e.target.value }))}
                  className="rounded-md border border-stone-300 px-2 py-1 text-xs w-32"
                  placeholder="₹/hr"
                />
              </div>
            ))}
            {gaps.missing_offerings.map(off => (
              <div key={off} className="space-y-1 border-t border-amber-200/50 pt-2">
                <label className="text-xs text-stone-700 block" htmlFor={`off-${off}-price`}>
                  {humanize(off)}
                </label>
                <input
                  id={`off-${off}-price`}
                  aria-label={`${humanize(off)} price`}
                  type="number"
                  value={offeringValues[off]?.base_price ?? ''}
                  onChange={e => setOfferingValues(s => ({
                    ...s, [off]: { ...s[off], base_price: e.target.value }
                  }))}
                  className="rounded-md border border-stone-300 px-2 py-1 text-xs w-full"
                  placeholder="Base price (₹)"
                />
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={onSubmitManual}
              disabled={fill.isPending || !manualFillValid}
              className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {fill.isPending ? 'Saving…' : 'Fill and continue'}
            </button>
            <button
              onClick={() => skip.mutate()}
              disabled={skip.isPending}
              className="rounded-lg border border-stone-300 px-4 py-1.5 text-xs font-medium text-stone-700"
            >
              {skip.isPending ? 'Skipping…' : 'Skip — use defaults'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
