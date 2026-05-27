import { useDeleteAsset } from '../../api/proposals'
import type { SectionAsset, SectionType } from '../../types/proposal'

interface Props {
  proposalId: string
  type: SectionType
  assets: SectionAsset[]
}

export function AssetRow({ proposalId, type, assets }: Props) {
  const del = useDeleteAsset(proposalId)

  if (assets.length === 0) return null

  return (
    <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {assets.map((a) => (
        <li
          key={a.id}
          className="group relative overflow-hidden rounded-md border border-stone-200 bg-stone-50"
        >
          <div className="aspect-video w-full bg-stone-100">
            <img
              src={a.url ?? ''}
              alt={a.caption ?? a.prompt ?? `Asset ${a.id}`}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="flex items-center justify-between gap-2 px-2 py-1 text-xs">
            <span className="truncate text-stone-600">
              {a.caption ?? (a.ai_generated ? `AI · ${a.prompt ?? ''}` : 'Uploaded')}
            </span>
            <button
              type="button"
              aria-label={`Delete asset ${a.id}`}
              onClick={() => del.mutate({ type, asset_id: a.id })}
              className="text-stone-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
          {a.ai_generated ? (
            <span className="absolute right-1 top-1 rounded bg-stone-900/70 px-1 text-[10px] uppercase tracking-wide text-white">
              AI
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
