import { useEffect, useRef, useState } from 'react'
import type { Offering, Multiplier } from '../../types/rate-card'
import { DEFAULT_PAYLOAD, type RateCardPayload } from './types'
import { WizardShell } from './wizard-shell'
import { OfferingsStep } from './offerings-step'
import { HourlyRatesStep } from './hourly-rates-step'
import { MultipliersStep } from './multipliers-step'
import { GlobalsStep, type GlobalsValue } from './globals-step'
import { KNOWN_MULTIPLIERS } from './known-multipliers'

interface Props {
  onSubmit: (data: RateCardPayload) => void
  saving: boolean
}

const STEPS = [
  { title: 'Offerings & Packages',  subtitle: "What you sell, and how it's packaged" },
  { title: 'Hourly rates by role',  subtitle: 'Used by the cost-model when proposals need time-based pricing' },
  { title: 'Pricing multipliers',   subtitle: 'Adjustments the cost-model applies automatically based on proposal context' },
  { title: 'Defaults & policies',   subtitle: 'Used as the baseline for every proposal — can be overridden per project' },
] as const

export function RateCardWizard({ onSubmit, saving }: Props) {
  const [subStep, setSubStep] = useState(0)
  const [offerings, setOfferings] = useState<Record<string, Offering>>({})
  const [hourlyRates, setHourlyRates] = useState<Record<string, number>>({})
  const [multipliers, setMultipliers] = useState<Record<string, Multiplier>>({})
  const [globals, setGlobals] = useState<GlobalsValue>({
    pass_through_markup: DEFAULT_PAYLOAD.pass_through_markup,
    standard_options:    DEFAULT_PAYLOAD.standard_options,
    standard_revisions:  DEFAULT_PAYLOAD.standard_revisions,
  })
  const [notice, setNotice] = useState<string | null>(null)
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clear any pending notice-dismiss timer on unmount so an unmounted
  // wizard doesn't fire a stale setState.
  useEffect(() => {
    return () => {
      if (noticeTimerRef.current !== null) {
        clearTimeout(noticeTimerRef.current)
      }
    }
  }, [])

  const isLast = subStep === STEPS.length - 1
  const continueLabel = isLast ? 'Finish rate card →' : 'Save & Continue →'

  const advance = () => setSubStep((s) => Math.min(s + 1, STEPS.length - 1))
  const goBack  = () => setSubStep((s) => Math.max(s - 1, 0))

  const handleContinue = () => {
    if (!isLast) {
      advance()
      return
    }
    onSubmit(filterPayload(offerings, hourlyRates, multipliers, globals))
  }

  const handleSkip = () => {
    if (isLast) {
      // Skipping the last step submits the wizard — no notice (it's not a defer).
      handleContinue()
      return
    }
    advance()
    // Cancel any already-pending dismiss timer so successive skips don't stack.
    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current)
    }
    setNotice('You can fill this in later in Settings.')
    noticeTimerRef.current = setTimeout(() => {
      setNotice(null)
      noticeTimerRef.current = null
    }, 5000)
  }

  return (
    <WizardShell
      subStep={subStep}
      total={STEPS.length}
      title={STEPS[subStep].title}
      subtitle={STEPS[subStep].subtitle}
      onBack={subStep > 0 ? goBack : undefined}
      onSkip={handleSkip}
      onContinue={handleContinue}
      continueLabel={continueLabel}
      notice={notice ?? undefined}
      disabled={saving}
    >
      {subStep === 0 && <OfferingsStep    value={offerings}    onChange={setOfferings} />}
      {subStep === 1 && <HourlyRatesStep  value={hourlyRates}  onChange={setHourlyRates} />}
      {subStep === 2 && <MultipliersStep  value={multipliers}  onChange={setMultipliers} />}
      {subStep === 3 && <GlobalsStep      value={globals}      onChange={setGlobals} />}
    </WizardShell>
  )
}

function filterPayload(
  offerings: Record<string, Offering>,
  hourly_rates: Record<string, number>,
  multipliers: Record<string, Multiplier>,
  globals: GlobalsValue,
): RateCardPayload {
  // Offerings: keep if name is non-empty. Drop empty package rows within each.
  const cleanOfferings: Record<string, Offering> = {}
  for (const [code, off] of Object.entries(offerings)) {
    if (!off.name?.trim()) continue
    const cleanPackages: Record<string, typeof off.packages[string]> = {}
    for (const [k, pkg] of Object.entries(off.packages)) {
      if (pkg.base > 0 || pkg.description.trim()) cleanPackages[k] = pkg
    }
    cleanOfferings[code] = { ...off, packages: cleanPackages }
  }

  // Hourly rates: drop zero rates.
  const cleanRates: Record<string, number> = {}
  for (const [k, r] of Object.entries(hourly_rates)) {
    if (r > 0) cleanRates[k] = r
  }

  // Multipliers: merge defaults for known keys the user left untouched
  // (so the cost-model sees their canonical values); drop any with value <= 0.
  const cleanMults: Record<string, Multiplier> = {}
  for (const known of KNOWN_MULTIPLIERS) {
    const editing = multipliers[known.key]
    const value = editing?.value ?? known.defaultValue
    if (value > 0) {
      cleanMults[known.key] = { value, description: editing?.description ?? '' }
    }
  }
  for (const [k, m] of Object.entries(multipliers)) {
    if (KNOWN_MULTIPLIERS.some((kn) => kn.key === k)) continue
    if (m.value > 0) cleanMults[k] = m
  }

  return {
    version: DEFAULT_PAYLOAD.version,
    offerings: cleanOfferings,
    hourly_rates: cleanRates,
    multipliers: cleanMults,
    ...globals,
  }
}
