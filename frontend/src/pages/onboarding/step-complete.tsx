interface Props {
  onSubmit: () => void
  saving: boolean
}

export function StepComplete({ onSubmit, saving }: Props) {
  return (
    <div className="text-center space-y-6">
      <div className="mx-auto w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
        <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <div>
        <h2 className="text-lg font-semibold text-stone-900">You're all set</h2>
        <p className="mt-1 text-sm text-stone-500">
          Your agency profile is ready. Start creating proposals.
        </p>
      </div>
      <button
        onClick={onSubmit}
        disabled={saving}
        className="rounded-lg bg-stone-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
      >
        {saving ? 'Finishing...' : 'Go to Dashboard'}
      </button>
    </div>
  )
}
