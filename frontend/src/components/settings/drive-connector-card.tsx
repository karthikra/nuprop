import { useDriveSync } from '../../api/connectors'
import { formatApiError } from '../../api/client'

export function DriveConnectorCard() {
  const syncDrive = useDriveSync()
  const result = syncDrive.data
  const softError = result?.error

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 6H4l8 5 8-5zM4 8v10h16V8l-8 5-8-5z" />
          </svg>
        </div>
        <div>
          <h3 className="font-medium text-stone-900 text-sm">Google Drive</h3>
          <p className="text-xs text-stone-500">Search for past proposals, meeting notes, and contracts</p>
        </div>
      </div>

      <button
        onClick={() => syncDrive.mutate()}
        disabled={syncDrive.isPending}
        className="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-200 disabled:opacity-50"
      >
        {syncDrive.isPending ? 'Syncing...' : 'Sync Now'}
      </button>

      {/* Soft error from the backend (e.g., "Google not connected") */}
      {softError ? (
        <p className="mt-2 text-xs text-red-600">{softError}</p>
      ) : null}

      {/* Network / 5xx error */}
      {syncDrive.isError ? (
        <p className="mt-2 text-xs text-red-600">{formatApiError(syncDrive.error, 'Drive sync failed')}</p>
      ) : null}

      {/* Success */}
      {syncDrive.isSuccess && !softError && result ? (
        <p className="mt-2 text-xs text-green-600">
          Found {result.documents_found ?? 0} documents across {result.clients_synced ?? 0} clients.
        </p>
      ) : null}
    </div>
  )
}
