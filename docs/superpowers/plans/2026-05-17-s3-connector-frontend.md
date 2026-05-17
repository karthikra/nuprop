# S3 — Connector Frontend (Drive/Cal/Slack hooks + Slack OAuth callback) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the frontend half of M17–M19 — Drive/Calendar/Slack go through React Query with proper error feedback, the broken Slack OAuth round-trip closes via a new `/settings/slack-callback` route, and the 240-LOC `agency.tsx` is split into four per-connector card files. All gated by tests.

**Architecture:** Add 7 new TanStack hooks and 4 types to `api/connectors.ts`, mirroring the established Gmail pattern (`useSlackStatus` is a `useQuery` on `['slack-status']`; mutations invalidate that key). Extract each connector card into `components/settings/{gmail,drive,calendar,slack}-connector-card.tsx`. New `slack-callback.tsx` page mirrors `gmail-callback.tsx` exactly. `agency.tsx` becomes a thin composer (~80 LOC, down from ~240). Five new vitest files cover the cards + callback page. Zero backend changes — S1's `test_slack_oauth_csrf.py` already covers OAuth state security.

**Tech Stack:** React 19 + TypeScript + Vite + Tailwind (stone/indigo palette) + TanStack Query + Vitest + RTL + MSW (per-test-file handlers).

**Spec:** `docs/superpowers/specs/2026-05-17-s3-connector-frontend-design.md` (commit `889dc52`)

**Audit context:** `docs/superpowers/audits/2026-05-16-m16-m20-state-audit.md`

**Baseline (before S3):** 295 backend pytest passing (unchanged after S3 — no backend changes), 148 frontend vitest passing across 27 files. After S3: ≥168 frontend passing across ≥32 files.

---

## File Structure

**New frontend files:**

- `frontend/src/pages/settings/slack-callback.tsx` — handles Slack OAuth redirect (mirror of `gmail-callback.tsx`)
- `frontend/src/components/settings/gmail-connector-card.tsx` — extracted from `agency.tsx`, no behavior change
- `frontend/src/components/settings/drive-connector-card.tsx` — new, uses `useDriveSync`
- `frontend/src/components/settings/calendar-connector-card.tsx` — new, uses `useCalendarSync`
- `frontend/src/components/settings/slack-connector-card.tsx` — new, uses 5 Slack hooks
- `frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx`
- `frontend/src/components/settings/__tests__/drive-connector-card.test.tsx`
- `frontend/src/components/settings/__tests__/calendar-connector-card.test.tsx`
- `frontend/src/components/settings/__tests__/slack-connector-card.test.tsx`
- `frontend/src/pages/settings/__tests__/slack-callback.test.tsx`

**Modified frontend files:**

- `frontend/src/api/connectors.ts` — add 7 hooks (`useDriveSync`, `useCalendarSync`, `useSlackStatus`, `useSlackAuthUrl`, `useSlackCallback`, `useSlackSync`, `useSlackDisconnect`) + 4 types (`DriveSyncResult`, `CalendarSyncResult`, `SlackStatus`, `SlackSyncResult`)
- `frontend/src/pages/settings/agency.tsx` — remove inline `ConnectorSyncCard` and `SlackConnectorCard`, import the 4 new connector cards, slim to ~80 LOC
- `frontend/src/App.tsx` — add `<Route path="/settings/slack-callback" element={<SlackCallbackPage />} />` after the Gmail route + the import

**Total:** 10 new files + 3 modified files. No backend changes.

---

## Task 1: API hooks — add 7 hooks + 4 types to `api/connectors.ts`

**Files:**
- Modify: `frontend/src/api/connectors.ts`

- [ ] **Step 1: Append the new types and hooks**

Open `frontend/src/api/connectors.ts`. Append after the existing `useGmailDisconnect` function (currently ends around line 68):

```typescript


// ── S3: Drive/Calendar/Slack hooks ───────────────────────────────────────

export interface DriveSyncResult {
  clients_synced?: number
  documents_found?: number
  error?: string
}

export interface CalendarSyncResult {
  clients_synced?: number
  meetings_found?: number
  error?: string
}

export interface SlackStatus {
  connected: boolean
  configured: boolean
  workspace: string | null
  last_sync: string | null
}

export interface SlackSyncResult {
  clients_synced?: number
  mentions_found?: number
  error?: string
}

/** Sync Drive documents. Rides on Gmail's Google OAuth — only callable when
 *  Gmail is connected. The backend returns `{error: string}` on soft failures
 *  (e.g., "Google not connected") instead of a 4xx, so the caller must render
 *  both `mutation.isError` and `mutation.data?.error`. */
export function useDriveSync() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<DriveSyncResult>('/connectors/drive/sync')
      return data
    },
  })
}

/** Sync Calendar meetings. Same soft-error caveat as Drive. */
export function useCalendarSync() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<CalendarSyncResult>('/connectors/calendar/sync')
      return data
    },
  })
}

export function useSlackStatus() {
  return useQuery({
    queryKey: ['slack-status'],
    queryFn: async () => {
      const { data } = await api.get<SlackStatus>('/connectors/slack/status')
      return data
    },
  })
}

export function useSlackAuthUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.get<{ auth_url: string }>('/connectors/slack/auth-url')
      return data.auth_url
    },
  })
}

export function useSlackCallback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (params: { code: string; state: string }) => {
      const { data } = await api.post<{ connected: boolean; workspace: string }>(
        '/connectors/slack/callback',
        params,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}

export function useSlackSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SlackSyncResult>('/connectors/slack/sync')
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}

export function useSlackDisconnect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.delete('/connectors/slack')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['slack-status'] }),
  })
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 3: Run the existing frontend test suite to confirm no regression**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 148 passing (unchanged — no consumers of these hooks yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/connectors.ts
git commit -m "feat(S3): add useDriveSync, useCalendarSync, and 5 Slack hooks"
```

---

## Task 2: Extract `<GmailConnectorCard>` (pure refactor)

**Files:**
- Create: `frontend/src/components/settings/gmail-connector-card.tsx`
- Modify: `frontend/src/pages/settings/agency.tsx`

This task is a PURE refactor — no behavior change. Tasks 3 onwards add the new cards.

- [ ] **Step 1: Create the new component file**

Create `frontend/src/components/settings/gmail-connector-card.tsx`:

```typescript
import { useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect } from '../../api/connectors'

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
  )
}
```

- [ ] **Step 2: Update `agency.tsx`**

Open `frontend/src/pages/settings/agency.tsx`. Replace the entire file with:

```typescript
import { useState, useEffect } from 'react'
import { useAuthStore } from '../../stores/auth-store'
import { useGmailStatus } from '../../api/connectors'
import { GmailConnectorCard } from '../../components/settings/gmail-connector-card'
import { api } from '../../api/client'

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
```

This task extracts ONLY the Gmail card. The local `ConnectorSyncCard` and `SlackConnectorCard` functions stay inline — they get replaced by Tasks 4/5/6 + 7. Tasks 4-7 add the real per-connector cards; Task 8 removes these legacy inline functions entirely.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 4: Run the frontend test suite**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 148 passing (refactor — no behavior change).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/gmail-connector-card.tsx \
        frontend/src/pages/settings/agency.tsx
git commit -m "refactor(S3): extract GmailConnectorCard from agency.tsx"
```

---

## Task 3: Test for `<GmailConnectorCard>` (post-extract smoke)

**Files:**
- Create: `frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx`

- [ ] **Step 1: Write the test**

Create `frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { GmailConnectorCard } from '../gmail-connector-card'

describe('GmailConnectorCard', () => {
  it('shows the loading state while status is being fetched', () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, async () => {
        // Delay so the component renders in loading state
        await new Promise((r) => setTimeout(r, 50))
        return HttpResponse.json({
          connected: false, configured: true, email: null, last_sync: null, email_count: 0,
        })
      }),
    )
    renderWithProviders(<GmailConnectorCard />)
    expect(screen.getByText(/checking connection/i)).toBeInTheDocument()
  })

  it('shows the not-configured amber banner when configured=false', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: false, email: null, last_sync: null, email_count: 0 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText(/GOOGLE_CLIENT_ID/)).toBeInTheDocument(),
    )
  })

  it('shows the Connect Gmail button when configured but not connected', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: true, email: null, last_sync: null, email_count: 0 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect gmail/i })).toBeInTheDocument(),
    )
  })

  it('shows the connected state with sync + disconnect buttons', async () => {
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({
          connected: true,
          configured: true,
          email: 'owner@acme.example.com',
          last_sync: '2026-05-17T10:00:00Z',
          email_count: 42,
        }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText('owner@acme.example.com')).toBeInTheDocument(),
    )
    expect(screen.getByText('42')).toBeInTheDocument() // email_count
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && pnpm test --run -t GmailConnectorCard 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx
git commit -m "test(S3): GmailConnectorCard branches (loading/not-configured/connect/connected)"
```

---

## Task 4: `<DriveConnectorCard>` + test

**Files:**
- Create: `frontend/src/components/settings/drive-connector-card.tsx`
- Create: `frontend/src/components/settings/__tests__/drive-connector-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/drive-connector-card.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { DriveConnectorCard } from '../drive-connector-card'

describe('DriveConnectorCard', () => {
  it('renders the Sync Now button initially with no result', () => {
    renderWithProviders(<DriveConnectorCard />)
    expect(screen.getByText(/Google Drive/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.queryByText(/Found/i)).not.toBeInTheDocument()
  })

  it('shows the success result after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ clients_synced: 3, documents_found: 12 }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 12 documents across 3 clients/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the backend returns result.error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ error: 'Google not connected' }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Google not connected/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the network request fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/drive/sync`, () =>
        HttpResponse.json({ detail: 'AI service unavailable' }, { status: 503 }),
      ),
    )
    renderWithProviders(<DriveConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/AI service unavailable|drive sync failed/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t DriveConnectorCard 2>&1 | tail -10`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/settings/drive-connector-card.tsx`:

```typescript
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t DriveConnectorCard 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/drive-connector-card.tsx \
        frontend/src/components/settings/__tests__/drive-connector-card.test.tsx
git commit -m "feat(S3): DriveConnectorCard with soft + network error alerts"
```

---

## Task 5: `<CalendarConnectorCard>` + test

**Files:**
- Create: `frontend/src/components/settings/calendar-connector-card.tsx`
- Create: `frontend/src/components/settings/__tests__/calendar-connector-card.test.tsx`

Structurally identical to `DriveConnectorCard`, different endpoint, "meetings" instead of "documents".

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/calendar-connector-card.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { CalendarConnectorCard } from '../calendar-connector-card'

describe('CalendarConnectorCard', () => {
  it('renders the Sync Now button initially with no result', () => {
    renderWithProviders(<CalendarConnectorCard />)
    expect(screen.getByText(/Google Calendar/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeInTheDocument()
    expect(screen.queryByText(/Found/i)).not.toBeInTheDocument()
  })

  it('shows the success result after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ clients_synced: 5, meetings_found: 28 }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 28 meetings across 5 clients/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the backend returns result.error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ error: 'Google not connected' }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Google not connected/i)).toBeInTheDocument(),
    )
  })

  it('shows a red alert when the network request fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/connectors/calendar/sync`, () =>
        HttpResponse.json({ detail: 'Upstream error' }, { status: 503 }),
      ),
    )
    renderWithProviders(<CalendarConnectorCard />)
    await user.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() =>
      expect(screen.getByText(/Upstream error|calendar sync failed/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t CalendarConnectorCard 2>&1 | tail -10`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/settings/calendar-connector-card.tsx`:

```typescript
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t CalendarConnectorCard 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/calendar-connector-card.tsx \
        frontend/src/components/settings/__tests__/calendar-connector-card.test.tsx
git commit -m "feat(S3): CalendarConnectorCard with soft + network error alerts"
```

---

## Task 6: `<SlackConnectorCard>` + tests

**Files:**
- Create: `frontend/src/components/settings/slack-connector-card.tsx`
- Create: `frontend/src/components/settings/__tests__/slack-connector-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/slack-connector-card.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SlackConnectorCard } from '../slack-connector-card'

describe('SlackConnectorCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the not-configured message when configured=false', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: false, workspace: null, last_sync: null }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByText(/SLACK_CLIENT_ID/)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /connect slack/i })).not.toBeInTheDocument()
  })

  it('shows Connect Slack button when configured but not connected', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect slack/i })).toBeInTheDocument(),
    )
  })

  it('opens the popup with the returned auth URL when Connect Slack is clicked', async () => {
    const user = userEvent.setup()
    const windowOpen = vi.fn()
    vi.stubGlobal('open', windowOpen)
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
      http.get(`${API}/connectors/slack/auth-url`, () =>
        HttpResponse.json({ auth_url: 'https://slack.com/oauth/v2/authorize?state=signed.abc' }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect slack/i })).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /connect slack/i }))
    await waitFor(() =>
      expect(windowOpen).toHaveBeenCalledWith(
        'https://slack.com/oauth/v2/authorize?state=signed.abc',
        'slack-auth',
        expect.any(String),
      ),
    )
  })

  it('shows the connected state with workspace + sync + disconnect buttons', async () => {
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: '2026-05-17T10:00:00Z' }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^sync$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /disconnect/i })).toBeInTheDocument()
  })

  it('renders a green alert with mentions_found after a successful sync', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: '2026-05-17T10:00:00Z' }),
      ),
      http.post(`${API}/connectors/slack/sync`, () =>
        HttpResponse.json({ clients_synced: 2, mentions_found: 7 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^sync$/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 7 mentions across 2 clients/i)).toBeInTheDocument(),
    )
  })

  it('calls DELETE /connectors/slack when Disconnect is confirmed', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: null }),
      ),
      http.delete(`${API}/connectors/slack`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /disconnect/i }))
    await waitFor(() => expect(deleted).toBe(true))
  })

  it('does NOT call DELETE when the user cancels the confirm dialog', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: true, configured: true, workspace: 'Acme HQ', last_sync: null }),
      ),
      http.delete(`${API}/connectors/slack`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))

    renderWithProviders(<SlackConnectorCard />)
    await waitFor(() => expect(screen.getByText('Acme HQ')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /disconnect/i }))
    await new Promise((r) => setTimeout(r, 50))
    expect(deleted).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t SlackConnectorCard 2>&1 | tail -15`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/settings/slack-connector-card.tsx`:

```typescript
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
    const url = await getAuthUrl.mutateAsync()
    if (url) {
      window.open(url, 'slack-auth', 'width=600,height=700,left=200,top=100')
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
        <button
          onClick={handleConnect}
          disabled={getAuthUrl.isPending}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {getAuthUrl.isPending ? 'Connecting...' : 'Connect Slack'}
        </button>
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t SlackConnectorCard 2>&1 | tail -15`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/slack-connector-card.tsx \
        frontend/src/components/settings/__tests__/slack-connector-card.test.tsx
git commit -m "feat(S3): SlackConnectorCard with full OAuth/sync/disconnect parity"
```

---

## Task 7: `<SlackCallbackPage>` + test + route registration

**Files:**
- Create: `frontend/src/pages/settings/slack-callback.tsx`
- Create: `frontend/src/pages/settings/__tests__/slack-callback.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/settings/__tests__/slack-callback.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { SlackCallbackPage } from '../slack-callback'

describe('SlackCallbackPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the processing state and calls the callback endpoint', async () => {
    let calledWith: Record<string, unknown> | null = null
    server.use(
      http.post(`${API}/connectors/slack/callback`, async ({ request }) => {
        calledWith = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ connected: true, workspace: 'Acme HQ' })
      }),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc123&state=signed.xyz' })
    expect(screen.getByText(/connecting slack/i)).toBeInTheDocument()
    await waitFor(() => expect(calledWith).toEqual({ code: 'abc123', state: 'signed.xyz' }))
  })

  it('shows the success state after callback succeeds', async () => {
    server.use(
      http.post(`${API}/connectors/slack/callback`, () =>
        HttpResponse.json({ connected: true, workspace: 'Acme HQ' }),
      ),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc&state=x' })
    await waitFor(() =>
      expect(screen.getByText(/slack connected/i)).toBeInTheDocument(),
    )
  })

  it('shows the error state when the callback fails', async () => {
    server.use(
      http.post(`${API}/connectors/slack/callback`, () =>
        HttpResponse.json({ detail: 'invalid oauth state (signature_mismatch)' }, { status: 400 }),
      ),
    )
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback?code=abc&state=bad' })
    await waitFor(() =>
      expect(screen.getByText(/failed to connect slack/i)).toBeInTheDocument(),
    )
  })

  it('shows the error state when the code param is missing', async () => {
    renderWithProviders(<SlackCallbackPage />, { route: '/settings/slack-callback' })
    await waitFor(() =>
      expect(screen.getByText(/failed to connect slack/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t SlackCallbackPage 2>&1 | tail -10`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the page**

Create `frontend/src/pages/settings/slack-callback.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSlackCallback } from '../../api/connectors'

export function SlackCallbackPage() {
  const [searchParams] = useSearchParams()
  const callback = useSlackCallback()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')

    if (!code) {
      setStatus('error')
      return
    }

    callback.mutate(
      { code, state: state || '' },
      {
        onSuccess: () => {
          setStatus('success')
          // Close popup after brief delay; parent will refetch slack-status
          setTimeout(() => {
            if (window.opener) {
              window.opener.focus()
            }
            window.close()
          }, 1500)
        },
        onError: () => {
          setStatus('error')
        },
      }
    )
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-stone-50 flex items-center justify-center">
      <div className="text-center">
        {status === 'processing' && (
          <>
            <div className="animate-spin h-8 w-8 border-2 border-stone-900 border-t-transparent rounded-full mx-auto" />
            <p className="mt-4 text-sm text-stone-500">Connecting Slack...</p>
          </>
        )}
        {status === 'success' && (
          <>
            <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="mt-4 text-sm font-medium text-stone-900">Slack connected</p>
            <p className="text-xs text-stone-500 mt-1">This window will close automatically.</p>
          </>
        )}
        {status === 'error' && (
          <>
            <p className="text-sm text-red-600">Failed to connect Slack.</p>
            <button onClick={() => window.close()} className="mt-2 text-xs text-stone-500 underline">Close this window</button>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Register the route in `App.tsx`**

Open `frontend/src/App.tsx`. Find the existing import for `GmailCallbackPage`:

```typescript
import { GmailCallbackPage } from './pages/settings/gmail-callback'
```

Add immediately after it:

```typescript
import { SlackCallbackPage } from './pages/settings/slack-callback'
```

Find the existing route registration for `/settings/gmail-callback`:

```typescript
              <Route path="/settings/gmail-callback" element={<GmailCallbackPage />} />
```

Add immediately after it:

```typescript
              <Route path="/settings/slack-callback" element={<SlackCallbackPage />} />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t SlackCallbackPage 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 6: TypeScript clean**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/settings/slack-callback.tsx \
        frontend/src/pages/settings/__tests__/slack-callback.test.tsx \
        frontend/src/App.tsx
git commit -m "feat(S3): SlackCallbackPage closes the Slack OAuth loop"
```

---

## Task 8: Slim down `agency.tsx` to a thin composer

**Files:**
- Modify: `frontend/src/pages/settings/agency.tsx`

This removes the legacy inline `ConnectorSyncCard` and `SlackConnectorCard` functions (from Task 2, kept as scaffolding) and replaces them with the new per-connector card components from Tasks 4/5/6.

- [ ] **Step 1: Replace `agency.tsx` with the slim composer**

Open `frontend/src/pages/settings/agency.tsx`. Replace the entire file with:

```typescript
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 148 baseline + 4 (Task 3) + 4 (Task 4) + 4 (Task 5) + 7 (Task 6) + 4 (Task 7) = 171 passing across 32 files.

- [ ] **Step 4: Verify legacy inline calls are gone**

Run:
```bash
grep -n "api.post\|api.get" frontend/src/pages/settings/agency.tsx
```
Expected: zero results — all raw API calls in agency.tsx are gone (they're inside the per-connector cards' hooks now).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/agency.tsx
git commit -m "refactor(S3): slim agency.tsx to thin composer"
```

---

## Task 9: Acceptance checklist + merge prep

**Files:** none modified (verification only).

- [ ] **Step 1: Full backend suite (no changes expected)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 295 passing (unchanged).

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: ≥171 passing across 32 files (148 baseline + 23 new across 5 new test files).

- [ ] **Step 3: TypeScript + grep checks**

Run:
```bash
cd frontend && pnpm tsc --noEmit
```
Expected: clean.

Run:
```bash
grep -rn "api.post\|api.get\|api.delete" frontend/src/pages/settings/
```
Expected: only `slack-callback.tsx` lines using the hook (NO direct `api.*` calls).

Run:
```bash
grep -n "Slack" frontend/src/App.tsx
```
Expected: 2 matches (the `import { SlackCallbackPage }` line and the `<Route path="/settings/slack-callback" ...>` line).

- [ ] **Step 4: Manual smoke — Slack OAuth loop**

Start the dev stack (in two terminals):

```bash
# Terminal 1
cd /Users/karthikramesh/Developer/nuprop/.claude/worktrees/m16-m20-s3-connector-frontend/backend && \
  SLACK_CLIENT_ID="dummy-for-smoke" SLACK_CLIENT_SECRET="dummy" \
  ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  .venv/bin/uvicorn app.main:app --reload

# Terminal 2
cd /Users/karthikramesh/Developer/nuprop/.claude/worktrees/m16-m20-s3-connector-frontend/frontend && pnpm dev
```

Manually verify:
1. Log in, navigate to Settings.
2. Slack card shows "Connect Slack" (because configured=true but connected=false).
3. Click Connect Slack — popup opens (will fail at Slack's end with `dummy-for-smoke` client ID — that's OK, we're just verifying the URL is generated and the popup launches with a real `state` param).
4. Inspect the popup URL — should be `https://slack.com/oauth/v2/authorize?client_id=dummy-for-smoke&...&state=<body>.<sig>` — confirm the `state` has the `body.signature` shape from S1.
5. Manually craft a redirect: navigate the popup to `http://localhost:5173/settings/slack-callback?code=fake&state=<state-from-step-4>` — should show "Failed to connect Slack" because Slack would reject the fake code. The point is: the route loads, calls the backend, gets a structured 400, shows the error page. The loop is closed.

- [ ] **Step 5: Update HANDOFF + memory**

Open `docs/superpowers/HANDOFF.md`. Replace the line:

```markdown
| **S3** — Connector frontend + Slack callback + tests | 1.5d | M17-M19 frontend parity |
```

With:

```markdown
| ~~S3~~ — Connector frontend + Slack callback + tests | ~~1.5d~~ ✅ done 2026-05-17 | 7 new TanStack hooks (Drive/Cal sync + 5 Slack), 4 new connector cards extracted (`{gmail,drive,calendar,slack}-connector-card.tsx`), Slack OAuth callback page closes the previously-broken round-trip, `agency.tsx` slimmed from 240→55 LOC. +23 vitest cases across 5 files. M17-M19 frontend parity. |
```

Update the "Active slice" line to S4:

```markdown
Each slice gets its own spec in `docs/superpowers/specs/`, its own worktree, and a user-approval checkpoint at the end. **Active slice: S4** (production OAuth wiring — needs user's hands).
```

Update `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md` to flip S3 to DONE and set "NEXT" to S4.

Commit the handoff change:

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S3): mark slice complete in handoff"
```

- [ ] **Step 6: Merge prep**

When the user approves at the S3 checkpoint:

```bash
# From the worktree, show the S3 commits
git log --oneline origin/main..HEAD

# Then from the main checkout:
cd /Users/karthikramesh/Developer/nuprop
git fetch origin
git merge --ff-only worktree-m16-m20-s3-connector-frontend
git push origin main
```

GitHub Actions auto-deploy from S1 will pick this up. The 2 new routes (`/settings/slack-callback`) and 4 new components are inert until users hit the settings page; Slack OAuth still needs S4's secret wiring to work in prod (currently `SLACK_CLIENT_ID` etc. aren't set on Fly).

---

## What lands next (S4 preview)

After S3 merges and approval: open worktree `m16-m20-s4-prod-oauth`. This is the slice that needs your hands more than the AI's:

1. Register a Google Cloud OAuth app: create project, OAuth consent screen, add scopes (gmail.readonly, drive.metadata.readonly, calendar.readonly), generate client ID + secret, add `https://nuprop.fly.dev/settings/gmail-callback` as an authorized redirect URI.
2. Register a Slack OAuth app at api.slack.com/apps: enable user scopes (search:read, channels:history, channels:read), add `https://nuprop.fly.dev/settings/slack-callback` as a redirect URL, generate client ID + secret.
3. Set Fly secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`, `ENCRYPTION_KEY` (Fernet — `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`).
4. Trigger a deploy (already auto-deploys on push but no code change to push — use `fly deploy` manually OR push a `.fly-redeploy` no-op commit).
5. Smoke test the full OAuth round-trip end-to-end against `nuprop.fly.dev`.

Estimated 0.5 day, mostly third-party console clicks. The AI guides + verifies; the user clicks.
