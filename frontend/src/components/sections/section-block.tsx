import { useEffect, useRef, useState } from 'react'
import type { Section, SectionType } from '../../types/proposal'
import {
  usePatchSection,
  useRegenerateSection,
  useRefineSection,
} from '../../api/proposals'
import { SectionToolbar } from './section-toolbar'

interface Props {
  proposalId: string
  type: SectionType
  title: string
  section: Section
}

export function SectionBlock({ proposalId, type, title, section }: Props) {
  const [draft, setDraft] = useState(section.content)
  const [included, setIncluded] = useState(section.included)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setDraft(section.content)
    setIncluded(section.included)
  }, [section.content, section.included])

  const patch = usePatchSection(proposalId)
  const regenerate = useRegenerateSection(proposalId)
  const refine = useRefineSection(proposalId)

  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value
    setDraft(next)
    if (debounceRef.current !== null) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      patch.mutate({ type, patch: { content: next } })
      debounceRef.current = null
    }, 1000)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current)
    }
  }, [])

  const onRegenerate = () =>
    regenerate.mutate(type, {
      onSuccess: (result) => setDraft(result.section.content),
    })
  const onRefine = (instructions: string) =>
    refine.mutate({ type, instructions }, {
      onSuccess: (result) => setDraft(result.section.content),
    })
  const onToggleInclude = () => {
    const next = !included
    setIncluded(next)
    patch.mutate({ type, patch: { included: next } })
  }

  return (
    <article className={`rounded-xl border border-stone-200 bg-white p-5 ${included ? '' : 'opacity-50'}`}>
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-base font-semibold text-stone-900">{title}</h2>
      </header>

      {included ? (
        <textarea
          aria-label={title}
          value={draft}
          onChange={onChange}
          rows={Math.max(4, draft.split('\n').length)}
          className="w-full rounded-md border border-stone-200 px-3 py-2 text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-stone-300"
        />
      ) : (
        <p className="text-sm text-stone-500 italic">Excluded from this proposal.</p>
      )}

      <div className="mt-3">
        <SectionToolbar
          isRegenerating={regenerate.isPending}
          isRefining={refine.isPending}
          isIncluded={included}
          onRegenerate={onRegenerate}
          onRefine={onRefine}
          onToggleInclude={onToggleInclude}
        />
      </div>
    </article>
  )
}
