import { useState } from 'react'

interface Props {
  isRegenerating: boolean
  isRefining: boolean
  isIncluded: boolean
  onRegenerate: () => void
  onRefine: (instructions: string) => void
  onToggleInclude: () => void
}

export function SectionToolbar({
  isRegenerating, isRefining, isIncluded,
  onRegenerate, onRefine, onToggleInclude,
}: Props) {
  const [showRefineField, setShowRefineField] = useState(false)
  const [refineText, setRefineText] = useState('')

  const submitRefine = () => {
    const text = refineText.trim()
    if (!text) return
    onRefine(text)
    setShowRefineField(false)
    setRefineText('')
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs">
        <button
          onClick={onRegenerate}
          disabled={isRegenerating || isRefining}
          className="rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 disabled:opacity-50"
        >
          {isRegenerating ? 'Regenerating…' : '↻ Regenerate'}
        </button>
        <button
          onClick={() => setShowRefineField(v => !v)}
          disabled={isRegenerating || isRefining}
          className="rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 disabled:opacity-50"
        >
          💬 Refine
        </button>
        <button
          onClick={onToggleInclude}
          className="ml-auto rounded-md border border-stone-200 px-2 py-1 hover:bg-stone-50 text-stone-600"
        >
          {isIncluded ? 'Exclude this section' : 'Re-include'}
        </button>
      </div>

      {showRefineField ? (
        <div className="rounded-md border border-stone-200 bg-stone-50 p-2 space-y-2">
          <label className="text-xs text-stone-600 block" htmlFor="refine-instructions">
            Refinement instructions
          </label>
          <textarea
            id="refine-instructions"
            aria-label="Refinement instructions"
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            rows={2}
            placeholder="e.g. Make it shorter and more formal"
            className="w-full rounded-md border border-stone-300 px-2 py-1 text-xs"
          />
          <div className="flex gap-2">
            <button
              onClick={submitRefine}
              disabled={isRefining || !refineText.trim()}
              className="rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {isRefining ? 'Applying…' : 'Apply refinement'}
            </button>
            <button
              onClick={() => { setShowRefineField(false); setRefineText('') }}
              className="rounded-md border border-stone-300 px-3 py-1 text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
