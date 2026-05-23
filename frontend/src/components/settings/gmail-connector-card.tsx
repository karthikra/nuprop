import { useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect } from '../../api/connectors'
import { formatApiError } from '../../api/client'

export function GmailConnectorCard() {
  const { data: gmailStatus, isLoading: loadingGmail } = useGmailStatus()
  const getAuthUrl = useGmailAuthUrl()
  const syncGmail = useGmailSync()
  const disconnectGmail = useGmailDisconnect()

  const handleConnect = async () => {
    const url = await getAuthUrl.mutateAsync()
    if (url) {
      window.open(url, 'gmail-auth', 'width=600,height=700,left=200,top=100')
    }
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
          <svg className="w-5 h-5 text-red-600" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20 18h-2V9.25L12 13 6 9.25V18H4V6h1.2l6.8 4.25L18.8 6H20v12zM20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-stone-900">Gmail</h3>
          <p className="text-xs text-stone-500">Sync email threads with client contacts for context intelligence</p>
        </div>
        {gmailStatus?.connected && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">Connected</span>
        )}
      </div>

      {loadingGmail ? (
        <p className="text-sm text-stone-400">Checking connection...</p>
      ) : !gmailStatus?.configured ? (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
          Google OAuth not configured. Add <code className="bg-amber-100 px-1 rounded">GOOGLE_CLIENT_ID</code> and <code className="bg-amber-100 px-1 rounded">GOOGLE_CLIENT_SECRET</code> to your .env file.
        </div>
      ) : !gmailStatus?.connected ? (
        <div className="space-y-3">
          <button
            onClick={handleConnect}
            disabled={getAuthUrl.isPending}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            {getAuthUrl.isPending ? 'Connecting...' : 'Connect Gmail'}
          </button>
          {getAuthUrl.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {formatApiError(getAuthUrl.error, 'Gmail connect failed')}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-stone-500">Account</p>
              <p className="font-medium text-stone-900">{gmailStatus.email}</p>
            </div>
            <div>
              <p className="text-stone-500">Emails Indexed</p>
              <p className="font-medium text-stone-900">{gmailStatus.email_count}</p>
            </div>
            <div>
              <p className="text-stone-500">Last Sync</p>
              <p className="font-medium text-stone-900">
                {gmailStatus.last_sync ? new Date(gmailStatus.last_sync).toLocaleString() : 'Never'}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => syncGmail.mutate()}
              disabled={syncGmail.isPending}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {syncGmail.isPending ? 'Syncing...' : 'Sync Now'}
            </button>
            <button
              onClick={() => { if (confirm('Disconnect Gmail? All indexed emails will be deleted.')) disconnectGmail.mutate() }}
              disabled={disconnectGmail.isPending}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
            >
              Disconnect
            </button>
          </div>
          {disconnectGmail.isError ? (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {formatApiError(disconnectGmail.error, 'Gmail disconnect failed')}
            </div>
          ) : null}
          {syncGmail.isSuccess && syncGmail.data && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">
              Synced {syncGmail.data.new_emails} new emails from {syncGmail.data.domains_synced.length} domains in {syncGmail.data.duration_seconds}s.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
