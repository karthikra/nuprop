import { useState } from 'react'
import { useContextBrief } from '../../api/clients'

interface ContextBriefToggleProps {
  clientId: string
}

export function ContextBriefToggle({ clientId }: ContextBriefToggleProps) {
  const [open, setOpen] = useState(false)
  const { data: brief, isLoading } = useContextBrief(clientId, open)

  return (
    <div className="mt-3 border-t border-indigo-200 pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs font-medium text-indigo-700 hover:text-indigo-900 inline-flex items-center gap-1"
      >
        <span aria-hidden>{open ? '▾' : '▸'}</span>
        {open ? 'Hide what the AI sees' : 'Show what the AI sees'}
      </button>

      {open ? (
        <div className="mt-2 rounded-lg bg-white border border-indigo-100 p-3 text-sm text-stone-700">
          {isLoading && brief == null ? (
            <p className="text-stone-400 text-xs">Generating brief...</p>
          ) : brief == null ? (
            <p className="text-stone-400 text-xs">Failed to load brief.</p>
          ) : !brief.has_context ? (
            <p className="text-stone-500 text-xs italic">No context to summarise yet. Paste some text above to get started.</p>
          ) : (
            <p className="whitespace-pre-wrap">{brief.brief}</p>
          )}
        </div>
      ) : null}
    </div>
  )
}
