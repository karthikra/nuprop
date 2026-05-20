import type { LookbackDays } from '../../../types/discovery'

interface Props {
  onPick: (days: LookbackDays) => void
  onCancel: () => void
}

const OPTIONS: { label: string; value: LookbackDays }[] = [
  { label: '30 days',  value: 30 },
  { label: '90 days',  value: 90 },
  { label: '365 days', value: 365 },
]

export function LookbackPicker({ onPick, onCancel }: Props) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-stone-900">Look back how far?</h2>
        <p className="mt-1 text-sm text-stone-500">
          We'll scan your Gmail inbox and suggest candidate clients based on who you've been emailing.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onPick(opt.value)}
            className={`rounded-lg border px-4 py-3 text-sm font-medium transition-colors ${
              opt.value === 90
                ? 'border-stone-900 bg-stone-900 text-white hover:bg-stone-800'
                : 'border-stone-300 bg-white text-stone-700 hover:bg-stone-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="flex justify-end">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
