import type { ChatMessage } from '../../types/proposal'

interface Props {
  message: ChatMessage
}

export function ResearchPlanCard({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const queries = (extra.queries as string[]) ?? []
  const rationale = (extra.rationale as string) ?? ''
  const title = phase === 'benchmarks' ? '📈 Benchmarks plan' : '🔍 Research plan'

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
        <p className="text-sm font-semibold text-slate-900 mb-3">{title}</p>
        {queries.length > 0 && (
          <>
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-1.5">I'll search for</p>
            <ul className="space-y-1 mb-3">
              {queries.map((q, i) => (
                <li key={i} className="text-sm text-slate-700">
                  <span className="text-slate-400">•</span> {q}
                </li>
              ))}
            </ul>
          </>
        )}
        {rationale && (
          <>
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-1.5">Why these queries</p>
            <p className="text-sm text-slate-700 leading-relaxed">{rationale}</p>
          </>
        )}
      </div>
    </div>
  )
}
