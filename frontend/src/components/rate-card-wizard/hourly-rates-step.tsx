import { useState } from 'react'
import { COMMON_ROLES } from './common-roles'
import { toSnakeKey } from './keys'

interface Props {
  value: Record<string, number>
  onChange: (next: Record<string, number>) => void
}

export function HourlyRatesStep({ value, onChange }: Props) {
  const [addingCustom, setAddingCustom] = useState(false)
  const [customName, setCustomName] = useState('')

  const availableChips = COMMON_ROLES.filter((r) => !(r.key in value))
  const rows = Object.entries(value)

  const addChip = (key: string) => onChange({ ...value, [key]: 0 })

  const updateRate = (key: string, rate: number) => onChange({ ...value, [key]: rate })

  const deleteRow = (key: string) => {
    const next = { ...value }
    delete next[key]
    onChange(next)
  }

  const commitCustom = () => {
    const trimmed = customName.trim()
    if (!trimmed) {
      setAddingCustom(false)
      return
    }
    const key = toSnakeKey(trimmed)
    if (!(key in value)) onChange({ ...value, [key]: 0 })
    setCustomName('')
    setAddingCustom(false)
  }

  const prettify = (key: string): string => {
    const common = COMMON_ROLES.find((r) => r.key === key)
    if (common) return common.label
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  return (
    <div className="space-y-4">
      {availableChips.length > 0 && (
        <>
          <p className="text-xs text-stone-500">Tap a common role to add it instantly</p>
          <div className="flex flex-wrap gap-2">
            {availableChips.map((r) => (
              <button
                key={r.key}
                onClick={() => addChip(r.key)}
                className="rounded-full border border-dashed border-stone-300 bg-stone-50 px-3 py-1 text-xs text-stone-600 hover:bg-stone-100"
              >
                + {r.label}
              </button>
            ))}
          </div>
        </>
      )}

      {rows.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-stone-400 uppercase tracking-wider">
              <th className="text-left py-2 font-medium">Role</th>
              <th className="text-right py-2 font-medium">Rate (₹/hr)</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map(([key, rate]) => (
              <tr key={key}>
                <td className="py-2 font-medium text-stone-900">{prettify(key)}</td>
                <td className="py-2 text-right">
                  <input
                    type="number"
                    aria-label={`Rate for ${prettify(key)}`}
                    value={rate}
                    onChange={(e) => updateRate(key, Number(e.target.value) || 0)}
                    className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                  />
                </td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => deleteRow(key)}
                    aria-label={`Delete ${prettify(key)}`}
                    className="text-stone-300 hover:text-red-500 text-sm"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {addingCustom ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Role name (e.g. Motion Designer)"
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            onBlur={commitCustom}
            onKeyDown={(e) => { if (e.key === 'Enter') commitCustom() }}
            autoFocus
            className="w-64 rounded-md border border-stone-300 px-2 py-1 text-sm"
          />
        </div>
      ) : (
        <button
          onClick={() => setAddingCustom(true)}
          className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900"
        >
          + Add custom role
        </button>
      )}
    </div>
  )
}
