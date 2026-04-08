import { useState, useCallback, useRef } from 'react'
import { useUpdatePreferences } from '../../api/preferences'
import {
  LETTER_STRATEGIES, LETTER_OPENINGS, LETTER_LENGTHS,
  PRICING_MODELS, SCOPE_LEVELS, SITE_THEMES, PAYMENT_TERMS_OPTIONS,
} from '../../types/proposal'
import type { Proposal, ProposalPreferences } from '../../types/proposal'
import type { TemplateConfig } from '../../types/template'

interface Props {
  proposal: Proposal
  templateConfig?: TemplateConfig
}

function prettify(val: string): string {
  return val.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function PrefSelect({ label, value, templateDefault, options, onChange }: {
  label: string
  value: string | undefined
  templateDefault: string | undefined
  options: readonly string[]
  onChange: (val: string) => void
}) {
  const effective = value || templateDefault || options[0]
  const isOverridden = !!value && value !== templateDefault

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-medium text-stone-500">{label}</label>
        <span className={`text-[9px] ${isOverridden ? 'text-blue-500' : 'text-stone-300'}`}>
          {isOverridden ? 'custom' : 'template'}
        </span>
      </div>
      <select
        value={effective}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-stone-900"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>{prettify(opt)}</option>
        ))}
      </select>
    </div>
  )
}

export function PreferencePanel({ proposal, templateConfig }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const updatePrefs = useUpdatePreferences()
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const prefs: ProposalPreferences = (proposal.preferences || {}) as ProposalPreferences
  const nc = templateConfig?.narrative || {}
  const oc = templateConfig?.output || {}

  const handleChange = useCallback((key: string, value: string | string[]) => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      updatePrefs.mutate({ proposalId: proposal.id, prefs: { [key]: value } })
    }, 300)
  }, [proposal.id, updatePrefs])

  if (collapsed) {
    return (
      <aside className="w-10 border-l border-stone-200 bg-white flex-shrink-0 flex flex-col items-center pt-4">
        <button onClick={() => setCollapsed(false)} className="p-2 rounded-lg hover:bg-stone-100 text-stone-400" title="Show preferences">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0" />
          </svg>
        </button>
      </aside>
    )
  }

  return (
    <aside className="w-72 border-l border-stone-200 bg-white flex-shrink-0 overflow-y-auto hidden lg:block">
      <div className="p-4 border-b border-stone-100 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wide">Preferences</h3>
        <button onClick={() => setCollapsed(true)} className="p-1 rounded hover:bg-stone-100 text-stone-400">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="p-4 space-y-5">
        {/* Letter */}
        <div>
          <p className="text-[10px] font-semibold text-stone-300 uppercase tracking-widest mb-2">Letter</p>
          <div className="space-y-3">
            <PrefSelect label="Tone" value={prefs.letter_strategy} templateDefault={nc.letter_strategy} options={LETTER_STRATEGIES} onChange={(v) => handleChange('letter_strategy', v)} />
            <PrefSelect label="Opening" value={prefs.letter_opening} templateDefault={undefined} options={LETTER_OPENINGS} onChange={(v) => handleChange('letter_opening', v)} />
            <PrefSelect label="Length" value={prefs.letter_length} templateDefault={undefined} options={LETTER_LENGTHS} onChange={(v) => handleChange('letter_length', v)} />
            <div>
              <label className="text-xs font-medium text-stone-500 mb-1 block">Custom instructions</label>
              <textarea
                defaultValue={prefs.letter_custom_instructions || ''}
                onBlur={(e) => { if (e.target.value !== (prefs.letter_custom_instructions || '')) handleChange('letter_custom_instructions', e.target.value) }}
                placeholder="e.g. Mention Nasscom event..."
                rows={2}
                className="w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs resize-none focus:outline-none focus:ring-1 focus:ring-stone-900"
              />
            </div>
          </div>
        </div>

        {/* Pricing */}
        <div>
          <p className="text-[10px] font-semibold text-stone-300 uppercase tracking-widest mb-2">Pricing</p>
          <div className="space-y-3">
            <PrefSelect label="Model" value={prefs.pricing_model} templateDefault={undefined} options={PRICING_MODELS} onChange={(v) => handleChange('pricing_model', v)} />
            <PrefSelect label="Payment terms" value={prefs.payment_terms} templateDefault={undefined} options={PAYMENT_TERMS_OPTIONS} onChange={(v) => handleChange('payment_terms', v)} />
          </div>
        </div>

        {/* Scope */}
        <div>
          <p className="text-[10px] font-semibold text-stone-300 uppercase tracking-widest mb-2">Scope</p>
          <PrefSelect label="Detail level" value={prefs.scope_detail_level} templateDefault={nc.scope_detail_level} options={SCOPE_LEVELS} onChange={(v) => handleChange('scope_detail_level', v)} />
        </div>

        {/* Output */}
        <div>
          <p className="text-[10px] font-semibold text-stone-300 uppercase tracking-widest mb-2">Output</p>
          <PrefSelect label="Site theme" value={prefs.site_theme} templateDefault={oc.site_theme} options={SITE_THEMES} onChange={(v) => handleChange('site_theme', v)} />
        </div>
      </div>
    </aside>
  )
}
