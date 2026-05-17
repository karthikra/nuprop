import { useEffect, useState } from 'react'
import { useContextBrief, type ContextBrief } from '../../api/clients'

interface ContextBriefToggleProps {
  clientId: string
}

export function ContextBriefToggle({ clientId }: ContextBriefToggleProps) {
  const [open, setOpen] = useState(false)
  const [cached, setCached] = useState<ContextBrief | null>(null)
  const { data, isLoading } = useContextBrief(clientId, open && cached === null)

  // Once we receive data, store it in local state so close+reopen is instant
  // without hitting Bedrock again. Known limitation: this cache survives
  // `useResetContext` / `useContextSave` invalidation of the query key — the
  // user may see a stale brief until the component remounts (e.g., page
  // refresh). Tracked as S6 follow-up; the cross-mutation case is rare in
  // practice (user resets then immediately reopens the brief).
  useEffect(() => {
    if (data != null) {
      setCached(data)
    }
  }, [data])

  // Reset local cache when clientId changes — otherwise we'd render the
  // previous client's brief if this component instance is reused.
  useEffect(() => {
    setCached(null)
  }, [clientId])

  const brief = cached ?? data

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
