import { useNavigate } from 'react-router-dom'
import { useNotifications, useMarkRead } from '../../api/notifications'

const ALERT_ICONS: Record<string, string> = {
  first_view: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z',
  return_visit: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  pdf_download: 'M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  cta_click: 'M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122',
  high_engagement: 'M13 10V3L4 14h7v7l9-11h-7z',
  new_visitor: 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z',
}

function timeAgo(date: string): string {
  const diff = Date.now() - new Date(date).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

interface Props {
  onClose: () => void
}

export function NotificationDropdown({ onClose }: Props) {
  const navigate = useNavigate()
  const { data } = useNotifications(0, 10)
  const markRead = useMarkRead()

  const handleClick = (notif: { id: string; proposal_id: string; read_at: string | null }) => {
    if (!notif.read_at) {
      markRead.mutate(notif.id)
    }
    onClose()
    navigate(`/analytics/${notif.proposal_id}`)
  }

  return (
    <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-stone-200 bg-white shadow-lg z-50 overflow-hidden">
      <div className="px-4 py-3 border-b border-stone-100">
        <p className="text-sm font-semibold text-stone-900">Notifications</p>
      </div>
      <div className="max-h-80 overflow-y-auto">
        {!data?.items?.length ? (
          <p className="px-4 py-6 text-sm text-stone-400 text-center">No notifications yet.</p>
        ) : (
          data.items.map((n) => (
            <button
              key={n.id}
              onClick={() => handleClick(n)}
              className={`w-full text-left px-4 py-3 hover:bg-stone-50 transition-colors flex gap-3 ${
                !n.read_at ? 'bg-blue-50/50' : ''
              }`}
            >
              <svg className={`w-4 h-4 mt-0.5 flex-shrink-0 ${n.urgency === 'high' ? 'text-red-500' : 'text-stone-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={ALERT_ICONS[n.alert_type] || ALERT_ICONS.first_view} />
              </svg>
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${!n.read_at ? 'font-medium text-stone-900' : 'text-stone-600'}`}>
                  {n.message}
                </p>
                <p className="text-xs text-stone-400 mt-0.5">{timeAgo(n.sent_at)}</p>
              </div>
              {!n.read_at && (
                <div className="w-2 h-2 rounded-full bg-blue-500 mt-2 flex-shrink-0" />
              )}
            </button>
          ))
        )}
      </div>
    </div>
  )
}
