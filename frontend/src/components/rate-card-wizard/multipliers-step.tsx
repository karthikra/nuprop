import { useState } from 'react'
import type { Multiplier } from '../../types/rate-card'
import { KNOWN_MULTIPLIERS } from './known-multipliers'
import { toSnakeKey } from './keys'

interface Props {
  value: Record<string, Multiplier>
  onChange: (next: Record<string, Multiplier>) => void
}

export function MultipliersStep({ value, onChange }: Props) {
  const [addingCustom, setAddingCustom] = useState(false)
  const [customName, setCustomName] = useState('')
  const [customValue, setCustomValue] = useState('1.0')

  const updateFixed = (key: string, patch: Partial<Multiplier>) => {
    const current = value[key]
    const base = current ?? {
      value: KNOWN_MULTIPLIERS.find((m) => m.key === key)?.defaultValue ?? 1.0,
      description: '',
    }
    onChange({ ...value, [key]: { ...base, ...patch } })
  }

  const commitCustom = () => {
    const trimmed = customName.trim()
    const numericValue = parseFloat(customValue)
    if (!trimmed || !Number.isFinite(numericValue) || numericValue <= 0) {
      setAddingCustom(false)
      setCustomName('')
      setCustomValue('1.0')
      return
    }
    const key = toSnakeKey(trimmed)
    onChange({ ...value, [key]: { value: numericValue, description: '' } })
    setAddingCustom(false)
    setCustomName('')
    setCustomValue('1.0')
  }

  const customEntries = Object.entries(value).filter(
    ([k]) => !KNOWN_MULTIPLIERS.some((m) => m.key === k),
  )

  return (
    <div className="space-y-3">
      {KNOWN_MULTIPLIERS.map((m) => {
        const current = value[m.key]
        const displayValue = current?.value ?? m.defaultValue
        const displayDescription = current?.description ?? ''
        return (
          <div key={m.key} className="rounded-lg border border-stone-200 p-3">
            <div className="flex items-baseline justify-between mb-1">
              <div>
                <span className="text-sm font-medium text-stone-900">{m.label}</span>
                <span className="ml-2 font-mono text-xs text-stone-400">{m.key}</span>
              </div>
            </div>
            <p className="text-xs text-stone-500 mb-2">{m.help}</p>
            <div className="flex items-center gap-3">
              <label className="text-xs text-stone-500">Multiplier</label>
              <input
                type="number"
                step="0.01"
                aria-label={`Value for ${m.label}`}
                value={displayValue}
                onChange={(e) => updateFixed(m.key, { value: Number(e.target.value) || 0 })}
                className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <label className="text-xs text-stone-500 ml-2">Note</label>
              <input
                type="text"
                aria-label={`Description for ${m.label}`}
                placeholder="Optional description"
                value={displayDescription}
                onChange={(e) => updateFixed(m.key, { description: e.target.value })}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
            </div>
          </div>
        )
      })}

      {customEntries.map(([key, m]) => (
        <div key={key} className="rounded-lg border border-dashed border-stone-300 p-3">
          <div className="flex items-baseline justify-between mb-1">
            <span className="font-mono text-xs text-stone-600">{key}</span>
            <button
              onClick={() => {
                const next = { ...value }
                delete next[key]
                onChange(next)
              }}
              aria-label={`Delete ${key}`}
              className="text-stone-300 hover:text-red-500 text-xs"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-stone-500">Multiplier</label>
            <input
              type="number"
              step="0.01"
              aria-label={`Value for ${key}`}
              value={m.value}
              onChange={(e) => onChange({ ...value, [key]: { ...m, value: Number(e.target.value) || 0 } })}
              className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <label className="text-xs text-stone-500 ml-2">Note</label>
            <input
              type="text"
              value={m.description}
              onChange={(e) => onChange({ ...value, [key]: { ...m, description: e.target.value } })}
              className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
          </div>
        </div>
      ))}

      {addingCustom ? (
        <div className="rounded-lg border border-dashed border-stone-300 p-3 space-y-2">
          <p className="text-xs text-amber-700">
            Custom multipliers must be applied manually in the proposal — the cost-model only auto-applies the four above.
          </p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Multiplier name (e.g. New client)"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm"
              autoFocus
            />
            <input
              type="number"
              step="0.01"
              placeholder="Value (e.g. 1.2)"
              value={customValue}
              onChange={(e) => setCustomValue(e.target.value)}
              className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <button
              onClick={commitCustom}
              className="rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white"
            >
              Save custom
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAddingCustom(true)}
          className="text-xs text-stone-600 border-b border-dashed border-stone-400 hover:text-stone-900"
        >
          + Add custom multiplier
        </button>
      )}
    </div>
  )
}
