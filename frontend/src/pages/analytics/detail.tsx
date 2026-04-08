import { useParams, useNavigate } from 'react-router-dom'
import { useProposalAnalytics, useProposalVisitors } from '../../api/analytics'

const SCORE_FACTORS = [
  { key: 'opened_within_24h', label: 'Opened within 24h', max: 10 },
  { key: 'time_on_site', label: 'Time on site', max: 20 },
  { key: 'sections_viewed', label: 'Sections viewed', max: 15 },
  { key: 'cards_expanded', label: 'Cards expanded', max: 15 },
  { key: 'investment_time', label: 'Investment section time', max: 10 },
  { key: 'pdf_downloaded', label: 'PDF downloaded', max: 5 },
  { key: 'return_visits', label: 'Return visits', max: 15 },
  { key: 'cta_clicked', label: 'CTA clicked', max: 10 },
] as const

function classificationColor(c: string) {
  if (c === 'hot' || c === 'ready') return 'text-green-600 bg-green-50 border-green-200'
  if (c === 'warm') return 'text-amber-600 bg-amber-50 border-amber-200'
  if (c === 'cool') return 'text-blue-600 bg-blue-50 border-blue-200'
  return 'text-stone-500 bg-stone-50 border-stone-200'
}

function formatDuration(seconds: number): string {
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${seconds}s`
}

export function AnalyticsDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: analytics, isLoading } = useProposalAnalytics(id!)
  const { data: visitors } = useProposalVisitors(id!)

  if (isLoading) return <p className="text-sm text-stone-400">Loading...</p>
  if (!analytics) return <p className="text-sm text-stone-500">Proposal not found.</p>

  const bd = analytics.engagement_breakdown

  return (
    <div>
      <button onClick={() => navigate('/analytics')} className="text-sm text-stone-500 hover:text-stone-700 mb-3">
        &larr; Back to analytics
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">{analytics.project_name}</h1>
          <p className="mt-0.5 text-sm text-stone-500">{analytics.client_name}</p>
        </div>
        <div className={`rounded-xl border px-4 py-3 text-center ${classificationColor(bd.classification)}`}>
          <p className="text-3xl font-bold">{analytics.engagement_score}</p>
          <p className="text-xs font-medium capitalize">{bd.classification}</p>
        </div>
      </div>

      {/* Quick stats */}
      <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <p className="text-xs text-stone-500">Total Views</p>
          <p className="mt-1 text-xl font-semibold">{analytics.total_views}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <p className="text-xs text-stone-500">Unique Visitors</p>
          <p className="mt-1 text-xl font-semibold">{analytics.unique_visitors}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <p className="text-xs text-stone-500">Avg Time</p>
          <p className="mt-1 text-xl font-semibold">{formatDuration(Math.round(analytics.avg_time_seconds))}</p>
        </div>
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <p className="text-xs text-stone-500">Last Viewed</p>
          <p className="mt-1 text-sm font-medium">
            {analytics.last_viewed_at ? new Date(analytics.last_viewed_at).toLocaleString() : '—'}
          </p>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Score breakdown */}
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Engagement Breakdown</h3>
          <div className="space-y-3">
            {SCORE_FACTORS.map((f) => {
              const val = bd[f.key as keyof typeof bd] as number
              const pct = (val / f.max) * 100
              return (
                <div key={f.key}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-stone-600">{f.label}</span>
                    <span className="font-medium text-stone-900">{val}/{f.max}</span>
                  </div>
                  <div className="h-2 rounded-full bg-stone-100">
                    <div
                      className="h-2 rounded-full bg-stone-900 transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Section heatmap */}
        <div className="rounded-xl border border-stone-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Section Time</h3>
          {analytics.most_viewed_sections.length === 0 ? (
            <p className="text-sm text-stone-400">No section data yet.</p>
          ) : (
            <div className="space-y-3">
              {analytics.most_viewed_sections.map((s) => {
                const maxTime = analytics.most_viewed_sections[0]?.total_time_seconds || 1
                const pct = (s.total_time_seconds / maxTime) * 100
                return (
                  <div key={s.section_id}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-stone-600 capitalize">{s.section_id}</span>
                      <span className="font-medium text-stone-900">{formatDuration(s.total_time_seconds)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-blue-50">
                      <div className="h-2 rounded-full bg-blue-400 transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Visitors */}
      <div className="mt-8">
        <h3 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Visitors</h3>
        {!visitors?.length ? (
          <p className="text-sm text-stone-400">No visitors yet.</p>
        ) : (
          <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-stone-50 text-left text-xs font-medium text-stone-500 uppercase tracking-wider">
                  <th className="px-4 py-3">Visitor</th>
                  <th className="px-4 py-3">Device</th>
                  <th className="px-4 py-3 text-center">Sessions</th>
                  <th className="px-4 py-3 text-center">Time</th>
                  <th className="px-4 py-3 text-center">Scroll</th>
                  <th className="px-4 py-3 text-center">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {visitors.map((v) => (
                  <tr key={v.id} className="hover:bg-stone-50">
                    <td className="px-4 py-3 font-mono text-xs text-stone-500">{v.fingerprint.slice(0, 8)}...</td>
                    <td className="px-4 py-3 text-stone-600 capitalize">{v.device_types.join(', ') || '—'}</td>
                    <td className="px-4 py-3 text-center">{v.session_count}</td>
                    <td className="px-4 py-3 text-center">{formatDuration(v.total_time_seconds)}</td>
                    <td className="px-4 py-3 text-center">{v.max_scroll_depth}%</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${classificationColor(v.classification)}`}>
                        {v.engagement_score}
                      </span>
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
