import { useCalendarSync } from '../../api/connectors'
import { formatApiError } from '../../api/client'

export function CalendarConnectorCard() {
  const syncCalendar = useCalendarSync()
  const result = syncCalendar.data
  const softError = result?.error

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <h3 className="font-medium text-stone-900 text-sm">Google Calendar</h3>
          <p className="text-xs text-stone-500">Analyze meeting frequency and attendee patterns</p>
        </div>
      </div>

      <button
        onClick={() => syncCalendar.mutate()}
        disabled={syncCalendar.isPending}
        className="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-200 disabled:opacity-50"
      >
        {syncCalendar.isPending ? 'Syncing...' : 'Sync Now'}
      </button>

      {softError ? (
        <p className="mt-2 text-xs text-red-600">{softError}</p>
      ) : null}

      {syncCalendar.isError ? (
        <p className="mt-2 text-xs text-red-600">{formatApiError(syncCalendar.error, 'Calendar sync failed')}</p>
      ) : null}

      {syncCalendar.isSuccess && !softError && result ? (
        <p className="mt-2 text-xs text-green-600">
          Found {result.meetings_found ?? 0} meetings across {result.clients_synced ?? 0} clients.
        </p>
      ) : null}
    </div>
  )
}
