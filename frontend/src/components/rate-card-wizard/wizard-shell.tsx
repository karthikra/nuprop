import type { ReactNode } from 'react'

interface Props {
  subStep: number
  total: number
  title: string
  subtitle: string
  children: ReactNode
  onBack?: () => void
  onSkip: () => void
  onContinue: () => void
  continueLabel?: string
  notice?: string
  disabled?: boolean
}

export function WizardShell({
  subStep,
  total,
  title,
  subtitle,
  children,
  onBack,
  onSkip,
  onContinue,
  continueLabel = 'Save & Continue →',
  notice,
  disabled,
}: Props) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <div className="px-5 py-4 border-b border-stone-200">
        <div className="flex gap-1.5 mb-2" aria-label={`Sub-step ${subStep + 1} of ${total}`}>
          {Array.from({ length: total }).map((_, i) => (
            <div
              key={i}
              data-testid="wizard-dot"
              data-active={i === subStep ? 'true' : 'false'}
              className={`w-1.5 h-1.5 rounded-full ${i === subStep ? 'bg-stone-900' : 'bg-stone-300'}`}
            />
          ))}
        </div>
        <h2 className="text-base font-semibold text-stone-900">{title}</h2>
        <p className="text-xs text-stone-500 mt-0.5">{subtitle}</p>
      </div>

      <div className="px-5 py-5">{children}</div>

      {notice && (
        <div className="px-5 py-2 text-xs text-amber-800 bg-amber-50 border-t border-amber-200">
          {notice}
        </div>
      )}

      <div className="px-5 py-3 border-t border-stone-200 bg-stone-50 flex items-center justify-between">
        <div className="flex gap-3 text-xs text-stone-500">
          {onBack && (
            <button onClick={onBack} className="hover:text-stone-900">
              ← Back
            </button>
          )}
          <button onClick={onSkip} className="hover:text-stone-900">
            Skip this section
          </button>
        </div>
        <button
          onClick={onContinue}
          disabled={disabled}
          className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-stone-800 disabled:opacity-50 disabled:pointer-events-none"
        >
          {continueLabel}
        </button>
      </div>
    </div>
  )
}
