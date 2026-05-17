import { useAuthStore } from '../../stores/auth-store'
import { useGmailStatus } from '../../api/connectors'
import { GmailConnectorCard } from '../../components/settings/gmail-connector-card'
import { DriveConnectorCard } from '../../components/settings/drive-connector-card'
import { CalendarConnectorCard } from '../../components/settings/calendar-connector-card'
import { SlackConnectorCard } from '../../components/settings/slack-connector-card'

export function AgencySettingsPage() {
  const agency = useAuthStore((s) => s.agency)
  const { data: gmailStatus } = useGmailStatus()

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

        <GmailConnectorCard />

        {/* Drive + Calendar (use same Google OAuth as Gmail) */}
        {gmailStatus?.connected && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <DriveConnectorCard />
            <CalendarConnectorCard />
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
