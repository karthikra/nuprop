import { useState } from 'react'

interface Props {
  onSubmit: (data: Record<string, unknown>) => void
  saving: boolean
}

export function StepVoice({ onSubmit, saving }: Props) {
  const [voice, setVoice] = useState('')

  return (
    <div className="space-y-5">
      <p className="text-sm text-stone-600">
        Paste 2-3 paragraphs from a past proposal or marketing copy. This helps the AI match your writing style.
      </p>
      <textarea
        value={voice}
        onChange={(e) => setVoice(e.target.value)}
        placeholder="Paste a sample of your agency's writing here... This could be from a past proposal covering letter, your website about page, or any marketing copy that represents your voice."
        rows={10}
        className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
      />
      <div className="flex gap-3">
        <button
          onClick={() => onSubmit({ voice_profile: voice || 'No voice sample provided — use confident, professional tone.' })}
          disabled={saving}
          className="flex-1 rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {saving ? 'Saving...' : voice ? 'Save & Continue' : 'Skip & Continue'}
        </button>
      </div>
    </div>
  )
}
