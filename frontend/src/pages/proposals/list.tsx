import { Link } from 'react-router-dom'
import { useProposals } from '../../api/proposals'
import { STATUS_COLOURS } from '../../types/proposal'

export function ProposalListPage() {
  const { data: proposals, isLoading } = useProposals()

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Proposals</h1>
          <p className="mt-1 text-sm text-stone-500">{proposals?.length ?? 0} proposals</p>
        </div>
        <Link
          to="/proposals/new"
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
        >
          New Proposal
        </Link>
      </div>

      <div className="mt-6 space-y-2">
        {isLoading && <p className="text-sm text-stone-400">Loading...</p>}
        {proposals?.length === 0 && !isLoading && (
          <div className="rounded-xl border border-dashed border-stone-300 bg-white p-12 text-center">
            <p className="text-stone-500 text-sm">No proposals yet.</p>
            <Link
              to="/proposals/new"
              className="mt-3 inline-block rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
            >
              Create your first proposal
            </Link>
          </div>
        )}
        {proposals?.map((p) => (
          <Link
            key={p.id}
            to={`/proposals/${p.id}`}
            className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 transition-colors"
          >
            <div className="min-w-0">
              <p className="font-medium text-stone-900 truncate">{p.project_name}</p>
              <p className="mt-0.5 text-xs text-stone-500">{p.client_name}</p>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0 ml-4">
              <span className="text-xs text-stone-400">
                {new Date(p.updated_at).toLocaleDateString()}
              </span>
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${
                  STATUS_COLOURS[p.status] || 'bg-stone-100 text-stone-600'
                }`}
              >
                {p.status}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
