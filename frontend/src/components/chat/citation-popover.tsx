export interface Citation {
  id: number
  url: string
  title: string
  domain: string
  cited_text: string
}

interface Props {
  citation: Citation
}

export function CitationPopover({ citation }: Props) {
  return (
    <div className="w-[400px] rounded-xl border border-slate-200 bg-white shadow-lg p-4 text-sm">
      <div className="flex items-start justify-between mb-1">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          {citation.domain}
        </span>
      </div>
      <p className="font-semibold text-slate-900 leading-snug mb-2">{citation.title}</p>
      <blockquote className="border-l-2 border-slate-300 pl-3 text-slate-700 italic mb-3 line-clamp-4">
        "{citation.cited_text}"
      </blockquote>
      <a
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-medium text-blue-600 hover:underline"
      >
        Open source ↗
      </a>
    </div>
  )
}
