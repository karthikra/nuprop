import { useState } from 'react'
import type { Offering, Package } from '../../types/rate-card'
import { nextOfferingCode, toSnakeKey } from './keys'

interface Props {
  value: Record<string, Offering>
  onChange: (next: Record<string, Offering>) => void
}

function prettify(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function OfferingsStep({ value, onChange }: Props) {
  const codes = Object.keys(value)
  const [preferredCode, setPreferredCode] = useState<string | null>(codes[0] ?? null)
  // Derive the actually-selected code: fall back to the first available
  // offering when the user's preferred code was deleted or re-keyed elsewhere.
  const selectedCode = preferredCode && preferredCode in value ? preferredCode : (codes[0] ?? null)
  const setSelectedCode = setPreferredCode

  const addOffering = () => {
    const code = nextOfferingCode(value)
    onChange({ ...value, [code]: { name: 'New offering', code, packages: {} } })
    setSelectedCode(code)
  }

  const deleteOffering = (code: string) => {
    if (!confirm(`Delete offering "${value[code].name}"?`)) return
    const next = { ...value }
    delete next[code]
    onChange(next)
    if (selectedCode === code) setSelectedCode(Object.keys(next)[0] ?? null)
  }

  const updateOffering = (code: string, patch: Partial<Offering>) => {
    if (patch.code && patch.code !== code) {
      const next = { ...value }
      if (patch.code in next) {
        // Code is already taken by another offering — silently drop the rename
        // to avoid clobbering. The user must pick a unique code.
        return
      }
      const oldOffering = next[code]
      delete next[code]
      next[patch.code] = { ...oldOffering, ...patch }
      onChange(next)
      setSelectedCode(patch.code)
    } else {
      onChange({ ...value, [code]: { ...value[code], ...patch } })
    }
  }

  const addPackage = (code: string) => {
    const offering = value[code]
    let key = 'new_package'
    let i = 1
    while (key in offering.packages) {
      key = `new_package_${++i}`
    }
    updateOffering(code, {
      packages: { ...offering.packages, [key]: { base: 0, description: '', typical_hours: 0 } },
    })
  }

  const updatePackage = (code: string, pkgKey: string, patch: Partial<Package>) => {
    const offering = value[code]
    updateOffering(code, {
      packages: { ...offering.packages, [pkgKey]: { ...offering.packages[pkgKey], ...patch } },
    })
  }

  const renamePackage = (code: string, oldKey: string, newName: string) => {
    const offering = value[code]
    const newKey = toSnakeKey(newName)
    if (newKey === oldKey || newKey in offering.packages) {
      updatePackage(code, oldKey, { description: offering.packages[oldKey].description })
      return
    }
    const nextPackages: Record<string, Package> = {}
    for (const [k, v] of Object.entries(offering.packages)) {
      nextPackages[k === oldKey ? newKey : k] = v
    }
    updateOffering(code, { packages: nextPackages })
  }

  const deletePackage = (code: string, pkgKey: string) => {
    const offering = value[code]
    const nextPackages = { ...offering.packages }
    delete nextPackages[pkgKey]
    updateOffering(code, { packages: nextPackages })
  }

  // selectedCode is the canonical map key. selected.code may temporarily drift during edits.
  const selected = selectedCode ? value[selectedCode] : null

  return (
    <div className="flex gap-4 min-h-[260px]">
      {/* Left rail */}
      <div className="w-1/3 border-r border-stone-200 pr-3 space-y-1">
        {codes.map((c) => (
          <div
            key={c}
            onClick={() => setSelectedCode(c)}
            className={`group flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer text-sm ${
              c === selectedCode ? 'bg-stone-900 text-white' : 'hover:bg-stone-100 text-stone-700'
            }`}
          >
            <span>{c} · {value[c].name}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteOffering(c) }}
              aria-label={`Delete offering ${value[c].name}`}
              className="opacity-0 group-hover:opacity-100 text-xs"
            >✕</button>
          </div>
        ))}
        <button
          onClick={addOffering}
          className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900 mt-2"
        >
          + Add offering
        </button>
      </div>

      {/* Right pane */}
      <div className="flex-1">
        {!selected && (
          <p className="text-sm text-stone-400 italic">Pick or add an offering to see its packages.</p>
        )}
        {selected && selectedCode && (
          <>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                aria-label="Offering name"
                value={selected.name}
                onChange={(e) => updateOffering(selectedCode, { name: e.target.value })}
                className="flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm font-medium"
              />
              <input
                type="text"
                aria-label="Offering code"
                value={selected.code}
                onChange={(e) => updateOffering(selectedCode, { code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '') })}
                maxLength={6}
                className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm font-mono"
              />
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-stone-400 uppercase">
                  <th className="text-left py-2 font-medium">Package</th>
                  <th className="text-left py-2 font-medium">Description</th>
                  <th className="text-right py-2 font-medium">Price (₹)</th>
                  <th className="text-right py-2 font-medium">Hours</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {Object.entries(selected.packages).map(([pkgKey, pkg]) => (
                  <tr key={pkgKey}>
                    <td className="py-2 pr-2">
                      <input
                        type="text"
                        aria-label={`Package name ${pkgKey}`}
                        defaultValue={prettify(pkgKey)}
                        onBlur={(e) => renamePackage(selectedCode, pkgKey, e.target.value)}
                        className="w-full rounded-md border border-transparent hover:border-stone-200 px-1 py-0.5 text-sm font-medium"
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        type="text"
                        aria-label={`Description for ${prettify(pkgKey)}`}
                        value={pkg.description}
                        onChange={(e) => updatePackage(selectedCode, pkgKey, { description: e.target.value })}
                        className="w-full rounded-md border border-transparent hover:border-stone-200 px-1 py-0.5 text-sm text-stone-600"
                      />
                    </td>
                    <td className="py-2 pr-2 text-right">
                      <input
                        type="number"
                        aria-label={`Price for ${prettify(pkgKey)}`}
                        value={pkg.base}
                        onChange={(e) => updatePackage(selectedCode, pkgKey, { base: Number(e.target.value) || 0 })}
                        className="w-24 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                      />
                    </td>
                    <td className="py-2 pr-2 text-right">
                      <input
                        type="number"
                        aria-label={`Hours for ${prettify(pkgKey)}`}
                        value={pkg.typical_hours ?? 0}
                        onChange={(e) => updatePackage(selectedCode, pkgKey, { typical_hours: Number(e.target.value) || 0 })}
                        className="w-16 rounded-md border border-stone-300 px-2 py-1 text-sm text-right"
                      />
                    </td>
                    <td className="py-2 text-right">
                      <button
                        onClick={() => deletePackage(selectedCode, pkgKey)}
                        aria-label={`Delete ${prettify(pkgKey)}`}
                        className="text-stone-300 hover:text-red-500 text-sm"
                      >✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <button
              onClick={() => addPackage(selectedCode)}
              className="text-xs text-stone-900 border-b border-dashed border-stone-400 hover:border-stone-900 mt-3"
            >
              + Add package
            </button>
          </>
        )}
      </div>
    </div>
  )
}
