import {
  useSlackStatus,
  useSlackAuthUrl,
  useSlackSync,
  useSlackDisconnect,
} from '../../api/connectors'
import { formatApiError } from '../../api/client'

export function SlackConnectorCard() {
  const { data: status, isLoading } = useSlackStatus()
  const getAuthUrl = useSlackAuthUrl()
  const syncSlack = useSlackSync()
  const disconnectSlack = useSlackDisconnect()

  const handleConnect = async () => {
    try {
      const url = await getAuthUrl.mutateAsync()
      if (url) {
        window.open(url, 'slack-auth', 'width=600,height=700,left=200,top=100')
      }
    } catch {
      // React Query captures the error in getAuthUrl.isError; the inline
      // red block below renders it. Nothing more to do at the call site.
    }
  }

  const handleDisconnect = () => {
    if (!confirm('Disconnect Slack?')) return
    disconnectSlack.mutate()
  }

  const syncResult = syncSlack.data
  const syncSoftError = syncResult?.error

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
          <span className="text-purple-600 font-bold text-sm">#</span>
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-stone-900">Slack</h3>
          <p className="text-xs text-stone-500">Search internal discussions about clients</p>
        </div>
        {status?.connected ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">Connected</span>
        ) : null}
      </div>

      {isLoading ? (
        <p className="text-sm text-stone-400">Checking connection...</p>
      ) : !status?.configured ? (
        <p className="text-xs text-stone-400">Set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET to enable.</p>
      ) : !status?.connected ? (
        <div className="space-y-3">
          <button
            onClick={handleConnect}
            disabled={getAuthUrl.isPending}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {getAuthUrl.isPending ? 'Connecting...' : 'Connect Slack'}
          </button>
          {getAuthUrl.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {formatApiError(getAuthUrl.error, 'Slack connect failed')}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-stone-500">Workspace</p>
              <p className="font-medium text-stone-900">{status.workspace}</p>
            </div>
            <div>
              <p className="text-stone-500">Last Sync</p>
              <p className="font-medium text-stone-900">
                {status.last_sync ? new Date(status.last_sync).toLocaleString() : 'Never'}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => syncSlack.mutate()}
              disabled={syncSlack.isPending}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {syncSlack.isPending ? 'Syncing...' : 'Sync'}
            </button>
            <button
              onClick={handleDisconnect}
              disabled={disconnectSlack.isPending}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {disconnectSlack.isPending ? 'Disconnecting...' : 'Disconnect'}
            </button>
          </div>

          {syncSoftError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">{syncSoftError}</div>
          ) : null}

          {syncSlack.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {formatApiError(syncSlack.error, 'Slack sync failed')}
            </div>
          ) : null}

          {disconnectSlack.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {formatApiError(disconnectSlack.error, 'Slack disconnect failed')}
            </div>
          ) : null}

          {syncSlack.isSuccess && !syncSoftError && syncResult ? (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">
              Found {syncResult.mentions_found ?? 0} mentions across {syncResult.clients_synced ?? 0} clients.
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
