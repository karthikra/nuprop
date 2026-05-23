# S7 — Frontend Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three frontend UX gaps deferred from S2/S3/rate-card wizard — make `ContextBriefToggle` honor cache invalidation, surface `getAuthUrl`/`disconnect` errors on the Gmail and Slack connector cards, and wire the rate-card wizard's amber skip-notice with a 5s auto-dismiss.

**Architecture:** Frontend-only. Replace `ContextBriefToggle`'s home-rolled cache with React Query's own cache (set `staleTime` and `gcTime` on the query). Surface unrendered mutation errors with the existing `formatApiError` inline-red-block pattern. Add `notice` state + a single `setTimeout` cleanup pattern to `RateCardWizard` to drive the already-existing `WizardShell.notice` prop.

**Tech Stack:** React 18, TypeScript, React Query v5, vitest + `@testing-library/react` + MSW, `userEvent`. `asyncio_mode = "auto"` is the backend pattern — this slice is frontend-only.

**Spec:** `docs/superpowers/specs/2026-05-23-s7-frontend-followups-design.md`

**Working directory:** all paths below are relative to `frontend/`. Run all commands from `frontend/`.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `src/api/clients.ts` | `useContextBrief` gains `staleTime` + `gcTime` so React Query owns the close+reopen cache | Modify |
| `src/components/clients/context-brief-toggle.tsx` | Drop the local `cached` state; render directly from `data` | Modify |
| `src/components/clients/__tests__/context-brief-toggle.test.tsx` | Add an invalidation-triggers-refetch test | Modify |
| `src/components/settings/gmail-connector-card.tsx` | Render `getAuthUrl.isError` and `disconnectGmail.isError` blocks | Modify |
| `src/components/settings/__tests__/gmail-connector-card.test.tsx` | Two new tests for the two new error paths | Modify |
| `src/components/settings/slack-connector-card.tsx` | Render `getAuthUrl.isError` and `disconnectSlack.isError` blocks | Modify |
| `src/components/settings/__tests__/slack-connector-card.test.tsx` | Two new tests for the two new error paths | Modify |
| `src/components/rate-card-wizard/rate-card-wizard.tsx` | Wire `notice` state + 5s timer + cleanup | Modify |
| `src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx` | Three new tests: notice shows on intermediate skip, dismisses after 5s, does NOT show on last-step skip | Modify |
| `docs/superpowers/HANDOFF.md` | Mark S7 complete | Modify |

---

### Task 1: ContextBriefToggle — drop local cache, use React Query

**Files:**
- Modify: `frontend/src/api/clients.ts` (the `useContextBrief` function at the bottom of the file)
- Modify: `frontend/src/components/clients/context-brief-toggle.tsx`
- Modify: `frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx` (append one new test)

- [ ] **Step 1: Write the failing test**

Append this test to `src/components/clients/__tests__/context-brief-toggle.test.tsx`, inside the existing `describe('ContextBriefToggle', () => { ... })` block, immediately before the closing `})`:

```tsx
  it('refetches the brief after the query is invalidated (e.g. after context save/reset)', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        calls += 1
        return HttpResponse.json({
          brief: calls === 1 ? 'first brief' : 'second brief',
          has_context: true,
          email_count: 0,
        })
      }),
    )
    const { queryClient } = renderWithProviders(<ContextBriefToggle clientId="c1" />)

    // Open the toggle — first fetch.
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/first brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)

    // Close the toggle.
    await user.click(screen.getByRole('button', { name: /hide what the AI sees/i }))

    // Simulate a context-save / context-reset mutation invalidating the brief query.
    await queryClient.invalidateQueries({ queryKey: ['client-context-brief', 'c1'] })

    // Reopen — must refetch because the query is now stale.
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/second brief/i)).toBeInTheDocument())
    expect(calls).toBe(2)
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm test -- src/components/clients/__tests__/context-brief-toggle.test.tsx`
Expected: the new test FAILS. With today's code, the local `cached` state is still set after the first fetch and the query is `enabled: open && cached === null` → the reopen sees `cached !== null` → query stays disabled → no refetch → `calls` stays at 1 and the assertion `expect(calls).toBe(2)` fails. The text `/second brief/i` also never appears (the rendered brief is still `cached.brief === 'first brief'`).

- [ ] **Step 3: Modify `useContextBrief` to own its cache**

In `frontend/src/api/clients.ts`, the current `useContextBrief` (last function in the file) reads:

```ts
export function useContextBrief(clientId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['client-context-brief', clientId],
    queryFn: async () => {
      const { data } = await api.get<ContextBrief>(
        `/clients/${clientId}/context-brief`,
      )
      return data
    },
    enabled: !!clientId && enabled,
  })
}
```

Replace it with:

```ts
export function useContextBrief(clientId: string, enabled: boolean) {
  // staleTime + gcTime let close+reopen serve from React Query's own cache
  // (5-minute window). After useContextSave / useResetContext invalidate this
  // query key, the next open refetches automatically.
  // gcTime overrides the test QueryClient's `gcTime: 0` default so the cache
  // actually survives the observer-gone period between close and reopen.
  return useQuery({
    queryKey: ['client-context-brief', clientId],
    queryFn: async () => {
      const { data } = await api.get<ContextBrief>(
        `/clients/${clientId}/context-brief`,
      )
      return data
    },
    enabled: !!clientId && enabled,
    staleTime: 5 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}
```

- [ ] **Step 4: Drop the local cache in `ContextBriefToggle`**

In `frontend/src/components/clients/context-brief-toggle.tsx`, replace the ENTIRE file content with:

```tsx
import { useState } from 'react'
import { useContextBrief } from '../../api/clients'

interface ContextBriefToggleProps {
  clientId: string
}

export function ContextBriefToggle({ clientId }: ContextBriefToggleProps) {
  const [open, setOpen] = useState(false)
  const { data: brief, isLoading } = useContextBrief(clientId, open)

  return (
    <div className="mt-3 border-t border-indigo-200 pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs font-medium text-indigo-700 hover:text-indigo-900 inline-flex items-center gap-1"
      >
        <span aria-hidden>{open ? '▾' : '▸'}</span>
        {open ? 'Hide what the AI sees' : 'Show what the AI sees'}
      </button>

      {open ? (
        <div className="mt-2 rounded-lg bg-white border border-indigo-100 p-3 text-sm text-stone-700">
          {isLoading && brief == null ? (
            <p className="text-stone-400 text-xs">Generating brief...</p>
          ) : brief == null ? (
            <p className="text-stone-400 text-xs">Failed to load brief.</p>
          ) : !brief.has_context ? (
            <p className="text-stone-500 text-xs italic">No context to summarise yet. Paste some text above to get started.</p>
          ) : (
            <p className="whitespace-pre-wrap">{brief.brief}</p>
          )}
        </div>
      ) : null}
    </div>
  )
}
```

The `ContextBrief` type import goes away (it's only used via `useContextBrief`'s return type). The two `useEffect`s and the `cached` / `setCached` state are gone.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pnpm test -- src/components/clients/__tests__/context-brief-toggle.test.tsx`
Expected: PASS — 6 tests pass (5 existing + 1 new). The "does not refetch on close + reopen (cached)" test continues to pass because `staleTime: 5 * 60 * 1000` and `gcTime: 5 * 60 * 1000` are set per-query and override the test QueryClient's `gcTime: 0` default.

- [ ] **Step 6: Commit**

```bash
git add src/api/clients.ts src/components/clients/context-brief-toggle.tsx src/components/clients/__tests__/context-brief-toggle.test.tsx
git commit -m "fix(S7): ContextBriefToggle refetches after invalidation"
```

---

### Task 2: Gmail connector card — surface getAuthUrl + disconnect errors

**Files:**
- Modify: `frontend/src/components/settings/gmail-connector-card.tsx`
- Modify: `frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx` (append two tests)

- [ ] **Step 1: Write the failing tests**

Append two tests to `src/components/settings/__tests__/gmail-connector-card.test.tsx`, inside the existing `describe('GmailConnectorCard', () => { ... })` block, immediately before its closing `})`:

```tsx
  it('renders an inline error when Connect Gmail (getAuthUrl) fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({ connected: false, configured: true, email: null, last_sync: null, email_count: 0 }),
      ),
      http.get(`${API}/connectors/gmail/auth-url`, () =>
        HttpResponse.json({ detail: 'OAuth provider unavailable' }, { status: 500 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    const connectBtn = await screen.findByRole('button', { name: /connect gmail/i })
    await user.click(connectBtn)
    await waitFor(() =>
      expect(screen.getByText(/OAuth provider unavailable/i)).toBeInTheDocument(),
    )
  })

  it('renders an inline error when Disconnect Gmail fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get(`${API}/connectors/gmail/status`, () =>
        HttpResponse.json({
          connected: true, configured: true, email: 'me@acme.com', last_sync: null, email_count: 0,
        }),
      ),
      http.delete(`${API}/connectors/gmail`, () =>
        HttpResponse.json({ detail: 'Disconnect failed' }, { status: 500 }),
      ),
    )
    renderWithProviders(<GmailConnectorCard />)
    const disconnectBtn = await screen.findByRole('button', { name: /^disconnect$/i })
    await user.click(disconnectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Disconnect failed/i)).toBeInTheDocument(),
    )
  })
```

Add the `vi` import to the existing imports at the top of that test file if not already present:

```tsx
import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
```

(The existing file currently imports `describe, it, expect` from vitest and probably does not import `userEvent` — add both lines.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- src/components/settings/__tests__/gmail-connector-card.test.tsx`
Expected: the two new tests FAIL — the error text never renders because the component has no isError blocks for `getAuthUrl` or `disconnectGmail`.

- [ ] **Step 3: Add the error blocks to the card**

In `frontend/src/components/settings/gmail-connector-card.tsx`, change the imports at the top from:

```tsx
import { useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect } from '../../api/connectors'
```

to:

```tsx
import { useGmailStatus, useGmailAuthUrl, useGmailSync, useGmailDisconnect } from '../../api/connectors'
import { formatApiError } from '../../api/client'
```

Inside the "not connected" branch (`!gmailStatus?.connected`), the current button reads:

```tsx
      ) : !gmailStatus?.connected ? (
        <button
          onClick={handleConnect}
          disabled={getAuthUrl.isPending}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {getAuthUrl.isPending ? 'Connecting...' : 'Connect Gmail'}
        </button>
      ) : (
```

Wrap the button in a `<div className="space-y-3">` and append an isError block. Replace those lines with:

```tsx
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
```

Inside the "connected" branch's `space-y-3` wrapper, the current success block is the last child:

```tsx
          {syncGmail.isSuccess && syncGmail.data && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">
              Synced {syncGmail.data.new_emails} new emails from {syncGmail.data.domains_synced.length} domains in {syncGmail.data.duration_seconds}s.
            </div>
          )}
        </div>
      )}
```

Add a `disconnectGmail.isError` block IMMEDIATELY BEFORE the success block (so it reads naturally — sync result OR disconnect failure):

```tsx
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
```

Change nothing else in the file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- src/components/settings/__tests__/gmail-connector-card.test.tsx`
Expected: PASS — all existing gmail tests still pass and the 2 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/components/settings/gmail-connector-card.tsx src/components/settings/__tests__/gmail-connector-card.test.tsx
git commit -m "fix(S7): surface gmail connect + disconnect errors on the card"
```

---

### Task 3: Slack connector card — surface getAuthUrl + disconnect errors

**Files:**
- Modify: `frontend/src/components/settings/slack-connector-card.tsx`
- Modify: `frontend/src/components/settings/__tests__/slack-connector-card.test.tsx` (append two tests)

- [ ] **Step 1: Write the failing tests**

Append two tests to `src/components/settings/__tests__/slack-connector-card.test.tsx`, inside the existing `describe('SlackConnectorCard', () => { ... })` block, immediately before its closing `})`:

```tsx
  it('renders an inline error when Connect Slack (getAuthUrl) fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({ connected: false, configured: true, workspace: null, last_sync: null }),
      ),
      http.get(`${API}/connectors/slack/auth-url`, () =>
        HttpResponse.json({ detail: 'Slack OAuth provider unavailable' }, { status: 500 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    const connectBtn = await screen.findByRole('button', { name: /connect slack/i })
    await user.click(connectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Slack OAuth provider unavailable/i)).toBeInTheDocument(),
    )
  })

  it('renders an inline error when Disconnect Slack fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    server.use(
      http.get(`${API}/connectors/slack/status`, () =>
        HttpResponse.json({
          connected: true, configured: true, workspace: 'acme-team', last_sync: null,
        }),
      ),
      http.delete(`${API}/connectors/slack`, () =>
        HttpResponse.json({ detail: 'Slack disconnect failed' }, { status: 500 }),
      ),
    )
    renderWithProviders(<SlackConnectorCard />)
    const disconnectBtn = await screen.findByRole('button', { name: /^disconnect$/i })
    await user.click(disconnectBtn)
    await waitFor(() =>
      expect(screen.getByText(/Slack disconnect failed/i)).toBeInTheDocument(),
    )
  })
```

Ensure the existing imports at the top of that test file include `vi` from vitest and `userEvent`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
```

(Add either or both if missing.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- src/components/settings/__tests__/slack-connector-card.test.tsx`
Expected: the two new tests FAIL — neither `getAuthUrl.isError` nor `disconnectSlack.isError` is currently rendered.

- [ ] **Step 3: Add the error blocks to the card**

In `frontend/src/components/settings/slack-connector-card.tsx`, the "not connected" branch is currently a bare `<button>`. Wrap it and add an isError block. Replace this block:

```tsx
      ) : !status?.connected ? (
        <button
          onClick={handleConnect}
          disabled={getAuthUrl.isPending}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {getAuthUrl.isPending ? 'Connecting...' : 'Connect Slack'}
        </button>
      ) : (
```

with:

```tsx
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
```

Inside the "connected" branch, the current error/success cascade is:

```tsx
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
```

Insert a `disconnectSlack.isError` block BETWEEN `syncSlack.isError` and `syncSlack.isSuccess`:

```tsx
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
```

Change nothing else in the file. `formatApiError` is already imported at the top.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- src/components/settings/__tests__/slack-connector-card.test.tsx`
Expected: PASS — existing slack tests still pass and the 2 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/components/settings/slack-connector-card.tsx src/components/settings/__tests__/slack-connector-card.test.tsx
git commit -m "fix(S7): surface slack connect + disconnect errors on the card"
```

---

### Task 4: Rate-card wizard — wire the timed skip-notice

**Files:**
- Modify: `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx`
- Modify: `frontend/src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx` (append three tests)

- [ ] **Step 1: Write the failing tests**

Append these three tests to `src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`, inside the existing `describe('RateCardWizard', () => { ... })` block, immediately before its closing `})`:

```tsx
  it('shows the amber skip-notice when an intermediate step is skipped', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.useFakeTimers()
    try {
      render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)
      await user.click(screen.getByRole('button', { name: /skip this section/i }))
      expect(
        screen.getByText(/you can fill this in later in settings/i),
      ).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('auto-dismisses the skip-notice after 5 seconds', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.useFakeTimers()
    try {
      render(<RateCardWizard onSubmit={vi.fn()} saving={false} />)
      await user.click(screen.getByRole('button', { name: /skip this section/i }))
      expect(
        screen.getByText(/you can fill this in later in settings/i),
      ).toBeInTheDocument()
      // Advance fake time past the 5-second dismiss timer.
      vi.advanceTimersByTime(5000)
      expect(
        screen.queryByText(/you can fill this in later in settings/i),
      ).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('does NOT show the skip-notice when the LAST step is skipped (submits instead)', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<RateCardWizard onSubmit={onSubmit} saving={false} />)

    // Advance to the last step via Save & Continue three times.
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))
    await user.click(screen.getByRole('button', { name: /save & continue/i }))

    // On the last step, "Skip this section" submits.
    await user.click(screen.getByRole('button', { name: /skip this section/i }))
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(
      screen.queryByText(/you can fill this in later in settings/i),
    ).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`
Expected: the three new tests FAIL — the notice never appears because `RateCardWizard` never passes `notice` to `WizardShell`.

- [ ] **Step 3: Wire the notice in `RateCardWizard`**

In `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx`, change the imports at the top from:

```tsx
import { useState } from 'react'
```

to:

```tsx
import { useEffect, useRef, useState } from 'react'
```

Inside the `RateCardWizard` component body, immediately after the existing `const [globals, setGlobals] = useState<GlobalsValue>({...})` block (the last `useState` call), add the notice state, a timer ref, and the cleanup `useEffect`:

```tsx
  const [notice, setNotice] = useState<string | null>(null)
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clear any pending notice-dismiss timer on unmount so an unmounted
  // wizard doesn't fire a stale setState.
  useEffect(() => {
    return () => {
      if (noticeTimerRef.current !== null) {
        clearTimeout(noticeTimerRef.current)
      }
    }
  }, [])
```

Replace the existing `onSkip={isLast ? handleContinue : advance}` line on the `WizardShell` with `onSkip={handleSkip}`, and add a `handleSkip` definition immediately above the `return (` statement (alongside `advance`, `goBack`, `handleContinue`):

```tsx
  const handleSkip = () => {
    if (isLast) {
      // Skipping the last step submits the wizard — no notice (it's not a defer).
      handleContinue()
      return
    }
    advance()
    // Cancel any already-pending dismiss timer so successive skips don't stack.
    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current)
    }
    setNotice('You can fill this in later in Settings.')
    noticeTimerRef.current = setTimeout(() => {
      setNotice(null)
      noticeTimerRef.current = null
    }, 5000)
  }
```

Then in the `<WizardShell ...>` props pass `notice={notice ?? undefined}`:

```tsx
    <WizardShell
      subStep={subStep}
      total={STEPS.length}
      title={STEPS[subStep].title}
      subtitle={STEPS[subStep].subtitle}
      onBack={subStep > 0 ? goBack : undefined}
      onSkip={handleSkip}
      onContinue={handleContinue}
      continueLabel={continueLabel}
      notice={notice ?? undefined}
      disabled={saving}
    >
```

(`WizardShell` types `notice` as `string | undefined`; coerce the `null` here.) Change nothing else in the file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx`
Expected: PASS — all existing wizard tests still pass and the 3 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/components/rate-card-wizard/rate-card-wizard.tsx src/components/rate-card-wizard/__tests__/rate-card-wizard.test.tsx
git commit -m "fix(S7): wire rate-card wizard skip-notice with 5s auto-dismiss"
```

---

### Task 5: Full regression + docs

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`

- [ ] **Step 1: Run the full frontend test suite**

Run: `pnpm test`
Expected: all pass. Baseline was 247; this slice adds:
- 1 test in `context-brief-toggle.test.tsx` (Task 1)
- 2 tests in `gmail-connector-card.test.tsx` (Task 2)
- 2 tests in `slack-connector-card.test.tsx` (Task 3)
- 3 tests in `rate-card-wizard.test.tsx` (Task 4)

Expected total: **255 passing**.

If anything fails, fix it before continuing — do not proceed with a red suite.

- [ ] **Step 2: Sanity-check the backend suite has not been touched**

From the repo root: `cd ../backend && .venv/bin/python -m pytest -q`
Expected: **359 passed** (the S6 number — S7 must not affect backend tests).

- [ ] **Step 3: Update `docs/superpowers/HANDOFF.md`**

In `docs/superpowers/HANDOFF.md` (relative to the repo root, so from `frontend/` it's `../docs/superpowers/HANDOFF.md`), update three places:

(a) The "Last updated" header — change to:

```
**Last updated:** 2026-05-23 (S7 frontend follow-ups shipped + deployed)
**Latest commit on `main`:** <fill in with the actual S7 merge commit SHA after the branch is merged>
**Working tree:** clean. On `main`. In sync with `origin/main`.
```

(Leave the SHA placeholder text for the controller to fill in at merge time — the implementer cannot know it yet.)

(b) Update the roadmap status line:

```
**M16-M20 roadmap status:** S1–S7 COMPLETE. All M16-M20 work — backend + frontend — is fully shipped.
```

(c) Append a new section heading immediately above the existing "What happened this session (2026-05-23)" section (which documents S6):

```markdown
## What happened this session (2026-05-23 — S7)

Shipped **S7 — frontend follow-ups**, the final M16-M20 slice. Three small UX gaps deferred from S2/S3/rate-card wizard:

- `ContextBriefToggle` now refetches after `useContextSave`/`useResetContext` invalidates the brief query. The local `cached` state was dropped in favor of React Query's own cache with `staleTime: 5 * 60 * 1000` and `gcTime: 5 * 60 * 1000` set on the query.
- Gmail and Slack connector cards now surface `getAuthUrl` and `disconnect` mutation errors using the existing `formatApiError` inline-red-block pattern. Drive and Calendar cards have no OAuth/disconnect and were left untouched.
- The rate-card wizard's `WizardShell.notice` prop is now wired: clicking "Skip this section" on an intermediate step shows "You can fill this in later in Settings." for 5 seconds. Last-step skip still submits (no notice). Timer is cleared on unmount and on consecutive skips.

### Test counts

- Frontend: **255 passing** (was 247 — +8 S7 tests)
- Backend: 359 passing (unchanged — S7 is frontend-only)
- Migration head: `03_proposal_context_brief` (no schema change)

S7 is the last roadmap slice. M16-M20 is done.
```

- [ ] **Step 4: Commit the doc change**

```bash
git add ../docs/superpowers/HANDOFF.md
git commit -m "docs(S7): mark S7 complete; M16-M20 roadmap finished"
```

(Run from `frontend/` — the `../` path resolves to the repo root.)

---

## Self-review notes

- **Spec coverage:** Piece A (brief cache) → Task 1; Piece B (connector errors) → Tasks 2 and 3; Piece C (skip-notice) → Task 4; regression + docs → Task 5.
- **Naming consistency:** `notice`, `noticeTimerRef`, `handleSkip`, `formatApiError`, `getAuthUrl.isError`, `disconnectGmail.isError`, `disconnectSlack.isError` are used identically wherever referenced.
- **Test-Client cache compatibility:** `useContextBrief` sets `gcTime: 5 * 60 * 1000` at the query level, which overrides the test `createTestQueryClient`'s `gcTime: 0` default. This is why the existing "does not refetch on close + reopen" test continues to pass with the new code.
- **userEvent + fake timers:** the wizard skip-notice tests use `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` so userEvent's internal waits don't deadlock against `vi.useFakeTimers()`. The third test (last-step skip) does NOT use fake timers because it doesn't need to advance time.
- **Last-step skip semantics:** in the third wizard test, the existing wizard already routes the last step's skip click through `handleContinue` (the spec preserves this). After this change, `handleSkip` short-circuits to `handleContinue()` on the last step and does NOT set the notice — verified against the test assertion that `onSubmit` is called and the notice text is NOT in the DOM.
