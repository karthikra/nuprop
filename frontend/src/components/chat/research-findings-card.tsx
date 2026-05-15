import { useState, useMemo } from 'react'
import type { ChatMessage } from '../../types/proposal'
import { CitationPopover, type Citation } from './citation-popover'

interface Span {
  start: number
  end: number
  citation_ids: number[]
}

interface Props {
  message: ChatMessage
}

/**
 * Splits ``content`` at ``span.end`` offsets and interleaves clickable
 * superscript markers. v1 renders plain prose with whitespace preserved;
 * proper markdown rendering can be retrofitted by replacing the segment
 * <p>{text}</p> with a <ReactMarkdown> call without changing the splitting
 * logic.
 */
function renderWithSpans(
  content: string,
  spans: Span[],
  citationsById: Map<number, Citation>,
): React.ReactNode[] {
  const sorted = [...spans].sort((a, b) => a.end - b.end)
  const out: React.ReactNode[] = []
  let cursor = 0
  for (let i = 0; i < sorted.length; i++) {
    const sp = sorted[i]
    const end = Math.min(sp.end, content.length)
    if (end <= cursor) continue
    out.push(content.slice(cursor, end))
    out.push(
      <CitationMarker
        key={`sup-${i}`}
        citationIds={sp.citation_ids}
        citationsById={citationsById}
      />,
    )
    cursor = end
  }
  if (cursor < content.length) out.push(content.slice(cursor))
  return out
}

function CitationMarker({
  citationIds,
  citationsById,
}: {
  citationIds: number[]
  citationsById: Map<number, Citation>
}) {
  const [hover, setHover] = useState(false)
  // For v1 only the first citation_id renders a popover; multi-id spans
  // are rare and we can iterate later.
  const id = citationIds[0]
  const citation = citationsById.get(id)
  return (
    <span className="relative inline-block">
      <sup
        data-citation-id={id}
        className="text-[10px] font-semibold text-blue-600 cursor-pointer ml-0.5"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        [{id}]
      </sup>
      {hover && citation && (
        <span className="absolute z-50 top-full mt-1 left-0">
          <CitationPopover citation={citation} />
        </span>
      )}
    </span>
  )
}

export function ResearchFindingsCard({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const citations = (extra.citations as Citation[]) ?? []
  const spans = (extra.spans as Span[]) ?? []

  const citationsById = useMemo(() => {
    const m = new Map<number, Citation>()
    for (const c of citations) m.set(c.id, c)
    return m
  }, [citations])

  const nodes = useMemo(
    () => renderWithSpans(message.content, spans, citationsById),
    [message.content, spans, citationsById],
  )

  const title = phase === 'benchmarks' ? '📊 Pricing benchmarks' : '📑 Research findings'
  const palette = phase === 'benchmarks' ? 'bg-amber-50 border-amber-200' : 'bg-blue-50 border-blue-200'

  return (
    <div className="flex justify-start">
      <div className={`max-w-[90%] rounded-2xl border ${palette} px-5 py-4`}>
        <p className="text-sm font-semibold text-slate-900 mb-3">{title}</p>
        <div className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
          {nodes}
        </div>
        {citations.length > 0 && (
          <>
            <hr className="my-3 border-slate-200" />
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-2">Sources</p>
            <ol className="space-y-1 text-xs">
              {citations.map((c) => (
                <li key={c.id} className="text-slate-700">
                  <span className="text-slate-400">[{c.id}]</span>{' '}
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                  >
                    {c.title}
                  </a>
                  <span className="text-slate-400"> · {c.domain}</span>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}
