import { Link } from 'react-router-dom'
import { useAnalyticsOverview } from '../../api/analytics'
import { STATUS_COLOURS } from '../../types/proposal'

const SCORE_COLOURS: Record<string, string> = {
  hot: 'bg-green-100 text-green-700',
  warm: 'bg-amber-100 text-amber-700',
  cool: 'bg-blue-100 text-blue-700',
  cold: 'bg-stone-100 text-stone-500',
}

function scoreBadge(score: number) {
  let cls = SCORE_COLOURS.cold
  if (score >= 61) cls = SCORE_COLOURS.hot
  else if (score >= 41) cls = SCORE_COLOURS.warm
  else if (score >= 21) cls = SCORE_COLOURS.cool
  return <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>{score}</span>
}

export function AnalyticsOverviewPage() {
  const { data: stats, isLoading } = useAnalyticsOverview()

  if (isLoading) return <p className="text-sm text-stone-400">Loading analytics...</p>

  return (
    <div>
      <h1 className="text-2xl font-semibold text-stone-900">Analytics</h1>
      <p className="mt-1 text-sm text-stone-500">Track engagement across your proposals.</p>

      {/* Stat cards */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Proposals Sent</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">{stats?.proposals_sent ?? 0}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Viewed Today</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">{stats?.proposals_viewed_today ?? 0}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Avg Engagement</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">{stats?.avg_engagement_score?.toFixed(0) ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <p className="text-sm font-medium text-stone-500">Win Rate</p>
          <p className="mt-2 text-3xl font-semibold text-stone-900">
            {stats?.win_rate != null ? `${(stats.win_rate * 100).toFixed(0)}%` : '—'}
          </p>
        </div>
      </div>

      {/* Proposals table */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-stone-900 mb-4">Proposals</h2>
        {!stats?.recent_proposals?.length ? (
          <div className="rounded-xl border border-dashed border-stone-300 bg-white p-8 text-center">
            <p className="text-sm text-stone-500">No proposals yet.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-stone-50 text-left text-xs font-medium text-stone-500 uppercase tracking-wider">
                  <th className="px-4 py-3">Project</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-center">Score</th>
                  <th className="px-4 py-3 text-center">Visitors</th>
                  <th className="px-4 py-3">Last Viewed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {stats.recent_proposals.map((p) => (
                  <tr key={p.proposal_id} className="hover:bg-stone-50">
                    <td className="px-4 py-3">
                      <Link to={`/analytics/${p.proposal_id}`} className="font-medium text-stone-900 hover:underline">
                        {p.project_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-stone-500">{p.client_name}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${STATUS_COLOURS[p.status] || 'bg-stone-100 text-stone-600'}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">{scoreBadge(p.engagement_score)}</td>
                    <td className="px-4 py-3 text-center text-stone-600">{p.unique_visitors}</td>
                    <td className="px-4 py-3 text-stone-400 text-xs">
                      {p.last_viewed_at ? new Date(p.last_viewed_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
