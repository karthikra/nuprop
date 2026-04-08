import { useState, useEffect } from 'react'
import { useAuthStore } from '../../stores/auth-store'
import { useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect } from '../../api/connectors'
import { api } from '../../api/client'

export function AgencySettingsPage() {
  const agency = useAuthStore((s) => s.agency)
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
    <div>
      <h1 className="text-2xl font-semibold text-stone-900">Settings</h1>
      <p className="mt-1 text-sm text-stone-500">Manage your agency profile and integrations.</p>

      {/* Agency Info */}
      <div className="mt-8 rounded-xl border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Agency Profile</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-stone-500">Agency Name</p>
            <p className="font-medium text-stone-900">{agency?.name || '—'}</p>
          </div>
          <div>
            <p className="text-stone-500">Currency</p>
            <p className="font-medium text-stone-900">{agency?.currency || 'INR'}</p>
          </div>
        </div>
      </div>

      {/* Connectors */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-stone-500 uppercase tracking-wide mb-4">Connectors</h2>

        {/* Gmail */}
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
            <button
              onClick={handleConnect}
              disabled={getAuthUrl.isPending}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {getAuthUrl.isPending ? 'Connecting...' : 'Connect Gmail'}
            </button>
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
              {syncGmail.isSuccess && syncGmail.data && (
                <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">
                  Synced {syncGmail.data.new_emails} new emails from {syncGmail.data.domains_synced.length} domains in {syncGmail.data.duration_seconds}s.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Drive + Calendar (use same Google OAuth as Gmail) */}
        {gmailStatus?.connected && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <ConnectorSyncCard
              name="Google Drive"
              description="Search for past proposals, meeting notes, and contracts"
              icon="M20 6H4l8 5 8-5zM4 8v10h16V8l-8 5-8-5z"
              syncEndpoint="/connectors/drive/sync"
              resultLabel="documents"
            />
            <ConnectorSyncCard
              name="Google Calendar"
              description="Analyze meeting frequency and attendee patterns"
              icon="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              syncEndpoint="/connectors/calendar/sync"
              resultLabel="meetings"
            />
          </div>
        )}

        {/* Slack */}
        <div className="mt-4">
          <SlackConnectorCard />
        </div>
      </div>
    </div>
  )
}

function ConnectorSyncCard({ name, description, icon, syncEndpoint, resultLabel }: {
  name: string; description: string; icon: string; syncEndpoint: string; resultLabel: string
}) {
  const [syncing, setSyncing] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const handleSync = async () => {
    setSyncing(true)
    try {
      const { data } = await api.post(syncEndpoint)
      setResult(data as Record<string, unknown>)
    } catch (err) {
      console.error(`${name} sync failed:`, err)
    }
    setSyncing(false)
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={icon} />
          </svg>
        </div>
        <div>
          <h3 className="font-medium text-stone-900 text-sm">{name}</h3>
          <p className="text-xs text-stone-500">{description}</p>
        </div>
      </div>
      <button onClick={handleSync} disabled={syncing} className="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-200 disabled:opacity-50">
        {syncing ? 'Syncing...' : 'Sync Now'}
      </button>
      {result != null ? (
        <p className="mt-2 text-xs text-green-600">
          Found {String((result as Record<string, unknown>)[`${resultLabel}_found`] || 0)} {resultLabel} across {String(result.clients_synced || 0)} clients.
        </p>
      ) : null}
    </div>
  )
}

function SlackConnectorCard() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.get('/connectors/slack/status').then(r => setStatus(r.data as Record<string, unknown>)).catch(() => {})
  }, [])

  const handleConnect = async () => {
    try {
      const { data } = await api.get<{ auth_url: string }>('/connectors/slack/auth-url')
      if (data.auth_url) window.open(data.auth_url, 'slack-auth', 'width=600,height=700')
    } catch { /* not configured */ }
  }

  const handleSync = async () => {
    setSyncing(true)
    try { await api.post('/connectors/slack/sync') } catch { /* ignore */ }
    setSyncing(false)
  }

  const isConnected = !!(status as Record<string, unknown> | null)?.connected
  const isConfigured = !!(status as Record<string, unknown> | null)?.configured

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
        {isConnected ? <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">Connected</span> : null}
      </div>
      {!isConfigured ? (
        <p className="text-xs text-stone-400">Set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET to enable.</p>
      ) : !isConnected ? (
        <button onClick={handleConnect} className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800">Connect Slack</button>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-sm text-stone-600">{String((status as Record<string, unknown>)?.workspace || '')}</span>
          <button onClick={handleSync} disabled={syncing} className="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-200 disabled:opacity-50">
            {syncing ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      )}
    </div>
  )
}
