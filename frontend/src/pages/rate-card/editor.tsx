import { useState } from 'react'
import { useActiveRateCard, useRateCardVersions, useUpdateRateCard, useCreateRateCardVersion } from '../../api/rate-cards'
import { InlineEditCell } from '../../components/rate-card/inline-edit-cell'
import type { RateCard, Offering, Package, Multiplier } from '../../types/rate-card'

const TABS = ['Packages', 'Hourly Rates', 'Multipliers'] as const
type Tab = (typeof TABS)[number]

function prettifyKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).replace(/^\d+\s*/, '')
}

export function RateCardEditorPage() {
  const { data: rateCard, isLoading } = useActiveRateCard()
  const { data: versions } = useRateCardVersions()
  const updateRateCard = useUpdateRateCard()
  const createVersion = useCreateRateCardVersion()
  const [activeTab, setActiveTab] = useState<Tab>('Packages')
  const [showVersionModal, setShowVersionModal] = useState(false)
  const [newVersion, setNewVersion] = useState('')

  if (isLoading) return <p className="text-sm text-stone-400">Loading rate card...</p>
  if (!rateCard) return (
    <div className="text-center py-12">
      <p className="text-stone-500">No rate card configured.</p>
      <p className="text-sm text-stone-400 mt-1">Set one up during onboarding or paste JSON in settings.</p>
    </div>
  )

  const save = (update: Partial<RateCard>) => {
    updateRateCard.mutate({ id: rateCard.id, ...update })
  }

  const handleCreateVersion = () => {
    if (!newVersion.trim()) return
    createVersion.mutate(newVersion.trim(), { onSuccess: () => { setShowVersionModal(false); setNewVersion('') } })
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Rate Card</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-sm font-medium text-stone-600">{rateCard.version}</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">Active</span>
            {versions && versions.length > 1 && (
              <span className="text-xs text-stone-400">({versions.length} versions)</span>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowVersionModal(true)}
          className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
        >
          Create New Version
        </button>
      </div>

      {/* Version modal */}
      {showVersionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-stone-900 mb-4">New Rate Card Version</h2>
            <p className="text-sm text-stone-500 mb-4">This clones the current rate card into a new version.</p>
            <input
              type="text"
              value={newVersion}
              onChange={(e) => setNewVersion(e.target.value)}
              placeholder="e.g. 2026-Q3"
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm mb-4"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowVersionModal(false)} className="px-4 py-2 text-sm text-stone-600">Cancel</button>
              <button
                onClick={handleCreateVersion}
                disabled={!newVersion.trim() || createVersion.isPending}
                className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {createVersion.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex gap-1 border-b border-stone-200">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'text-stone-900 border-b-2 border-stone-900'
                : 'text-stone-500 hover:text-stone-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="mt-6">
        {activeTab === 'Packages' && (
          <PackagesTab offerings={rateCard.offerings} onUpdate={(offerings) => save({ offerings })} />
        )}
        {activeTab === 'Hourly Rates' && (
          <HourlyRatesTab rates={rateCard.hourly_rates} onUpdate={(hourly_rates) => save({ hourly_rates })} />
        )}
        {activeTab === 'Multipliers' && (
          <MultipliersTab
            multipliers={rateCard.multipliers}
            passThrough={rateCard.pass_through_markup}
            standardOptions={rateCard.standard_options}
            standardRevisions={rateCard.standard_revisions}
            onUpdate={save}
          />
        )}
      </div>
    </div>
  )
}

// ── Packages Tab ──────────────────────────────────────────

function PackagesTab({ offerings, onUpdate }: {
  offerings: Record<string, Offering>
  onUpdate: (offerings: Record<string, Offering>) => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)

  const updatePackage = (offeringKey: string, pkgKey: string, field: keyof Package, value: number | string) => {
    const updated = { ...offerings }
    updated[offeringKey] = { ...updated[offeringKey], packages: { ...updated[offeringKey].packages } }
    updated[offeringKey].packages[pkgKey] = { ...updated[offeringKey].packages[pkgKey], [field]: value }
    onUpdate(updated)
  }

  const deletePackage = (offeringKey: string, pkgKey: string) => {
    if (!confirm(`Delete ${prettifyKey(pkgKey)}?`)) return
    const updated = { ...offerings }
    updated[offeringKey] = { ...updated[offeringKey], packages: { ...updated[offeringKey].packages } }
    delete updated[offeringKey].packages[pkgKey]
    onUpdate(updated)
  }

  return (
    <div className="space-y-2">
      {Object.entries(offerings).map(([key, offering]) => {
        const pkgCount = Object.keys(offering.packages || {}).length
        const isOpen = expanded === key
        return (
          <div key={key} className="rounded-xl border border-stone-200 bg-white overflow-hidden">
            <button
              onClick={() => setExpanded(isOpen ? null : key)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-stone-50 transition-colors text-left"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">{offering.code}</span>
                <span className="font-medium text-stone-900">{offering.name}</span>
                <span className="text-xs text-stone-400">{pkgCount} packages</span>
              </div>
              <svg className={`w-4 h-4 text-stone-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {isOpen && (
              <div className="border-t border-stone-100 px-5 py-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-stone-500 uppercase tracking-wider">
                      <th className="text-left py-2">Package</th>
                      <th className="text-left py-2">Description</th>
                      <th className="text-right py-2">Base Price</th>
                      <th className="text-right py-2">Hours</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-50">
                    {Object.entries(offering.packages || {}).map(([pkgKey, pkg]) => (
                      <tr key={pkgKey} className="hover:bg-stone-50">
                        <td className="py-2 font-medium text-stone-900">{prettifyKey(pkgKey)}</td>
                        <td className="py-2 text-stone-500 max-w-[200px] truncate" title={pkg.description}>{pkg.description}</td>
                        <td className="py-2 text-right">
                          <InlineEditCell value={pkg.base} format="currency" onSave={(v) => updatePackage(key, pkgKey, 'base', v as number)} />
                        </td>
                        <td className="py-2 text-right">
                          <InlineEditCell value={pkg.typical_hours || 0} format="number" onSave={(v) => updatePackage(key, pkgKey, 'typical_hours', v as number)} />
                        </td>
                        <td className="py-2">
                          <button onClick={() => deletePackage(key, pkgKey)} className="p-1 text-stone-300 hover:text-red-500">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Hourly Rates Tab ──────────────────────────────────────

function HourlyRatesTab({ rates, onUpdate }: {
  rates: Record<string, number>
  onUpdate: (rates: Record<string, number>) => void
}) {
  const updateRate = (key: string, value: number) => {
    onUpdate({ ...rates, [key]: value })
  }

  const deleteRate = (key: string) => {
    if (!confirm(`Delete ${prettifyKey(key)}?`)) return
    const updated = { ...rates }
    delete updated[key]
    onUpdate(updated)
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-stone-50 text-xs text-stone-500 uppercase tracking-wider">
            <th className="text-left px-5 py-3">Role</th>
            <th className="text-right px-5 py-3">Rate (₹/hr)</th>
            <th className="w-8 px-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {Object.entries(rates).map(([key, rate]) => (
            <tr key={key} className="hover:bg-stone-50">
              <td className="px-5 py-3 font-medium text-stone-900">{prettifyKey(key)}</td>
              <td className="px-5 py-3 text-right">
                <InlineEditCell value={rate} format="currency" onSave={(v) => updateRate(key, v as number)} />
              </td>
              <td className="px-2 py-3">
                <button onClick={() => deleteRate(key)} className="p-1 text-stone-300 hover:text-red-500">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Multipliers Tab ───────────────────────────────────────

function MultipliersTab({ multipliers, passThrough, standardOptions, standardRevisions, onUpdate }: {
  multipliers: Record<string, Multiplier>
  passThrough: number
  standardOptions: number
  standardRevisions: number
  onUpdate: (update: Partial<RateCard>) => void
}) {
  const updateMultiplier = (key: string, value: number) => {
    const updated = { ...multipliers }
    updated[key] = { ...updated[key], value }
    onUpdate({ multipliers: updated })
  }

  return (
    <div className="space-y-6">
      {/* Multipliers table */}
      <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-stone-50 text-xs text-stone-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Multiplier</th>
              <th className="text-right px-5 py-3">Value</th>
              <th className="text-left px-5 py-3">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {Object.entries(multipliers).map(([key, mult]) => (
              <tr key={key} className="hover:bg-stone-50">
                <td className="px-5 py-3 font-medium text-stone-900">{prettifyKey(key)}</td>
                <td className="px-5 py-3 text-right">
                  <InlineEditCell value={mult.value} format="number" onSave={(v) => updateMultiplier(key, v as number)} />
                </td>
                <td className="px-5 py-3 text-stone-500">{mult.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Global settings */}
      <div className="rounded-xl border border-stone-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Global Settings</h3>
        <div className="grid grid-cols-3 gap-6">
          <div>
            <label className="text-xs text-stone-500">Pass-through markup</label>
            <div className="mt-1">
              <InlineEditCell value={passThrough} format="percent" onSave={(v) => onUpdate({ pass_through_markup: v as number })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-stone-500">Standard options per deliverable</label>
            <div className="mt-1">
              <InlineEditCell value={standardOptions} format="number" onSave={(v) => onUpdate({ standard_options: v as number })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-stone-500">Standard revision rounds</label>
            <div className="mt-1">
              <InlineEditCell value={standardRevisions} format="number" onSave={(v) => onUpdate({ standard_revisions: v as number })} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
