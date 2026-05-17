# Spec — S3: Connector Frontend (Drive/Calendar/Slack hooks + Slack OAuth callback)

**Date:** 2026-05-17
**Slice:** S3 of S0–S6 M16-M20 finish-line (see [audit](../audits/2026-05-16-m16-m20-state-audit.md))
**Depends on:** S2 (manual context UI) merged to main at commit `583153f`
**Worktree:** `m16-m20-s3-connector-frontend`
**Owner:** Karthik
**Estimate:** 1.5 days
**Status:** spec — awaiting approval

---

## Goal

Close the frontend gaps for the M17–M19 connector trio. The S1-hardened backend has working OAuth flows for Gmail and Slack and sync endpoints for Drive/Calendar (riding on Gmail's OAuth), but the frontend uses raw `api.post()` calls for everything except Gmail, swallows errors with `.catch(() => {})`, and is missing the Slack OAuth callback route entirely (the popup launches with nowhere to redirect to in production). After S3, users can connect Slack from the settings page (the OAuth round-trip completes), see Drive/Calendar sync results with proper error feedback, and all of this surface has vitest coverage.

S1 hardened the backend; S2 shipped M16's user-facing flow; S3 ships M17–M19's user-facing flow. Pipeline integration of connector data into proposal generation is S5's slice.

---

## What "shipped" looks like

After S3 merges to `main`, all of the following are true:

1. **Slack OAuth round-trip works end-to-end.** New `/settings/slack-callback` route handles Slack's redirect after the user approves the popup — the page calls `POST /connectors/slack/callback` (which verifies S1's signed state), then closes the popup. The parent settings page invalidates `['slack-status']` and shows the workspace name.
2. **Drive/Calendar/Slack go through TanStack Query.** Five new React Query hooks in `api/connectors.ts` mirror the Gmail pattern. No more raw `api.post().catch(() => {})` in components.
3. **Error feedback on every sync.** Each connector card shows a red inline alert when a sync fails (network error OR backend `result.error` field). Same green alert pattern as Gmail's existing success message.
4. **Disconnect works for Slack.** Native `confirm()` dialog (matches Gmail's pattern), `useSlackDisconnect` mutation hits `DELETE /connectors/slack`, settings page rehydrates.
5. **Settings page slimmed.** `agency.tsx` reduced from 240 LOC to ~80 LOC by extracting each connector card into `components/settings/{gmail,drive,calendar,slack}-connector-card.tsx`. The Drive/Calendar cards only render when Gmail is connected (they ride on Gmail's OAuth).
6. **Tests cover each card + the callback page.** Five new vitest files. Frontend stays ≥168 passing across 32 files.
7. **No backend changes.** S3 is frontend-only. Drive/Calendar status and disconnect endpoints are NOT added in this slice (see D1).

### Explicit non-goals for S3

- Adding GET /drive/status, GET /calendar/status, DELETE /drive, DELETE /calendar on the backend (deferred — Drive/Cal share Gmail's Google OAuth and don't need independent connect/disconnect; "disconnect Gmail" wipes Google for all three).
- Persisting agency-level "last sync" or "indexed count" for Drive/Calendar (currently shown only from the most-recent sync's mutation data, lost on page reload).
- Replacing the inline alert system with a toast notification system (S3 keeps inline alerts).
- Playwright OAuth E2E smoke (manual smoke instead).
- Migrating chat `ContextCheck` to the S2 preview-then-save flow (still an S6 follow-up).
- Backend changes to `disconnect_slack` to delete indexed Slack data on disconnect (today it only removes the token; would be its own slice if desired).

---

## Architecture decisions

### D1 — Drive/Calendar hitch on Gmail; no separate status or disconnect

**Current backend reality:** `/connectors/drive/sync` and `/connectors/calendar/sync` exist. No `/status` or `/disconnect` for either. Both reuse Gmail's stored Google refresh token.

**Change:** Drive and Calendar cards are rendered ONLY when `gmailStatus?.connected === true`. They show just a "Sync Now" button and the latest sync result. No Connect/Disconnect — both are implicit via Gmail's connection.

**Why:** Matches reality. Adding `/drive/status` + `/drive/disconnect` (etc.) would be ~50 LOC of backend per connector with no real user value — disconnecting Drive while keeping Gmail connected doesn't free up any meaningful local state. If a user wants to stop using Drive, they can just not press Sync.

**Test surface:** `drive-connector-card.test.tsx` and `calendar-connector-card.test.tsx` (both follow identical patterns).

### D2 — Slack OAuth callback page mirrors Gmail's

**Current:** `frontend/src/pages/settings/gmail-callback.tsx` exists and handles Google's OAuth redirect. The route `/settings/gmail-callback` is registered in `App.tsx`. The popup-close pattern (`window.opener.focus(); window.close()` after 1.5s) is established.

**Change:** Add `frontend/src/pages/settings/slack-callback.tsx` with the same shape, just calling `useSlackCallback` instead of `useGmailCallback`. Register `/settings/slack-callback` in `App.tsx` immediately after the Gmail route.

**Why:** The backend's `SLACK_REDIRECT_URI` config defaults to `http://localhost:5173/settings/slack-callback`. Currently no route exists at that path → the OAuth flow is broken in prod. This is the single most urgent S3 fix.

**Test surface:** `slack-callback.test.tsx` — success (closes popup), network error (shows red), missing code (shows red).

### D3 — Each connector card lives in its own file

**Current:** `agency.tsx` is 240 LOC with `ConnectorSyncCard` (a generic Drive/Cal helper that uses raw `api.post`) and `SlackConnectorCard` (own inline `api.get/post`) co-located.

**Change:** Extract each connector into `frontend/src/components/settings/{gmail,drive,calendar,slack}-connector-card.tsx`. `agency.tsx` becomes a thin composer (~80 LOC) that imports + renders them.

**Why:** Each card has its own state, its own tests, its own visual variant. Co-location worked when there was only Gmail; with 4 connectors the file is too crowded. The S2 pattern (extract `ContextProfileCard` for the same reason) sets the precedent. The Gmail card is extracted too — small one-time refactor cost, larger long-term clarity.

**Test surface:** One vitest file per card.

### D4 — `result.error` rendered as a red alert alongside network errors

**Backend behaviour:** Some sync endpoints return `200 OK` with `{error: string}` instead of a 4xx when the upstream isn't ready (e.g., `sync_drive` returns `{error: "Google not connected"}` if Gmail isn't connected). This is a soft error pattern.

**Change:** Each connector card renders BOTH:
- `useDriveSync.isError ? <RedAlert text={formatApiError(useDriveSync.error, 'Drive sync failed')} /> : null`
- `useDriveSync.data?.error ? <RedAlert text={useDriveSync.data.error} /> : null`

Two error sources, same UI treatment. No transformation in the queryFn.

**Why:** Keeps the queryFn pure (just data passthrough). The "soft error" semantic is rare enough that mapping it back to a thrown exception inside the queryFn would surprise readers — better to handle both error shapes at the render layer where the difference is visible.

### D5 — Slack disconnect: native `confirm()`, simple copy, no backend changes

**Change:** `<SlackConnectorCard>` disconnect handler: `if (!confirm('Disconnect Slack?')) return; disconnectSlack.mutate()`.

**Why:** Matches the existing Gmail and the S2 reset-context patterns. Backend `disconnect_slack` only removes the token (no indexed data deletion) — copy reflects that. Optional more-elaborate "indexed data will remain" copy adds words without adding clarity.

### D6 — No backend tests in this slice

S1's `test_slack_oauth_csrf.py` already covers state issuance and verification. S3's frontend tests use MSW handlers that mimic the backend response shape — no real backend interaction. Adding redundant backend smoke tests dilutes the test suite without adding signal.

---

## File-by-file change list

**Frontend (new):**

- `frontend/src/pages/settings/slack-callback.tsx` — mirror of `gmail-callback.tsx`
- `frontend/src/components/settings/gmail-connector-card.tsx` — extracted from `agency.tsx`
- `frontend/src/components/settings/drive-connector-card.tsx` — new, uses `useDriveSync`
- `frontend/src/components/settings/calendar-connector-card.tsx` — new, uses `useCalendarSync`
- `frontend/src/components/settings/slack-connector-card.tsx` — new, uses Slack hooks
- `frontend/src/components/settings/__tests__/gmail-connector-card.test.tsx` — new (smoke after extract)
- `frontend/src/components/settings/__tests__/drive-connector-card.test.tsx` — new
- `frontend/src/components/settings/__tests__/calendar-connector-card.test.tsx` — new
- `frontend/src/components/settings/__tests__/slack-connector-card.test.tsx` — new
- `frontend/src/pages/settings/__tests__/slack-callback.test.tsx` — new

**Frontend (modified):**

- `frontend/src/api/connectors.ts` — add 7 new hooks: `useDriveSync`, `useCalendarSync`, `useSlackStatus`, `useSlackAuthUrl`, `useSlackCallback`, `useSlackSync`, `useSlackDisconnect` (the existing Gmail hooks stay) plus 4 new types: `DriveSyncResult`, `CalendarSyncResult`, `SlackStatus`, `SlackSyncResult`
- `frontend/src/pages/settings/agency.tsx` — remove inline `ConnectorSyncCard` and `SlackConnectorCard`; import 4 new connector cards; slim down to a thin composer
- `frontend/src/App.tsx` — add `<Route path="/settings/slack-callback" element={<SlackCallbackPage />} />` immediately after the Gmail route, plus the import

**Total:** 10 new files (5 components + 5 tests), 3 modified files.

---

## Open questions for review

**Q1 — Should `agency.tsx` extract `AgencyProfileCard` too while we're at it?**

Recommended: **no.** That section is a single block of static markup with no logic. Extracting would be unrelated to S3's scope and dilute the diff. Leave inline.

**Q2 — Should Drive/Cal cards have a small "Last synced just now" timestamp after a successful sync?**

Recommended: **no for S3.** The success alert already says "Synced X documents across Y clients". A separate timestamp would imply persistence (which doesn't exist for these endpoints). Add only if user testing reveals confusion.

**Q3 — Should we add a backend secret check for `SLACK_REDIRECT_URI` matching the deployed frontend URL in S4?**

Recommended: **yes but that's S4's job.** Document in the S4 plan that registering the Slack OAuth app requires updating `SLACK_REDIRECT_URI` (currently localhost) to the prod URL. Don't change anything in S3.

**Q4 — Should `useSlackCallback.onSuccess` close the popup itself or let the page do it?**

Recommended: **let the page do it** (matches Gmail's pattern). The hook is reusable; the popup-close behaviour is specific to the callback page's UX.

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Slack callback page mounts inside `AppShell` and renders with the sidebar (looks weird in popup) | Low — but check | Gmail callback uses the same pattern and works. The page's full-screen `min-h-screen flex items-center justify-center` covers the AppShell. Verify in manual smoke. |
| Drive/Cal cards render before `gmailStatus` resolves and flicker | Low | Wrap render in `gmailStatus?.connected && (...)` — same as the existing pattern. |
| Slack popup blocked by browser | Medium | Same risk Gmail has today. Add a fallback note in the connect button "If the popup didn't open, please disable your popup blocker". |
| `formatApiError` signature drift breaks compilation | Low | S2 already validated the (`err`, `fallback`) signature. Reuse the same call shape. |

---

## Acceptance test checklist (post-implementation)

- [ ] `cd backend && .venv/bin/python -m pytest -q` → 295 passing (unchanged — no backend changes).
- [ ] `cd frontend && pnpm test --run` → 148 baseline + ≥20 new tests across 5 new files ≈ 168+ passing across 32 files.
- [ ] `cd frontend && pnpm tsc --noEmit` → clean.
- [ ] Manual smoke: open dev stack, register, navigate to Settings → connect Gmail (popup → callback → workspace shown). Then Sync Gmail (alert appears). Then Sync Drive (alert appears). Then Sync Calendar (alert appears).
- [ ] Manual smoke: with SLACK_CLIENT_ID set in `.env`, click Connect Slack → popup opens at Slack OAuth → approve → popup redirects to `/settings/slack-callback` → spinner → "Slack connected" → popup closes → parent settings page shows workspace name.
- [ ] Manual smoke: click "Disconnect Slack" → confirm → settings page returns to "Connect Slack" button.
- [ ] `grep -rn "api.post(.*connectors" frontend/src/pages/settings/` returns zero results (all raw API calls replaced with hooks).

---

## What lands next (S4 preview)

After S3 merges and approval: open worktree `m16-m20-s4-prod-oauth`. This is the one slice that requires the user (not the AI) to do meaningful work — register Google + Slack OAuth apps in their respective consoles, generate client IDs/secrets, set 5 Fly secrets, update redirect URIs. Estimated 0.5 day, mostly clicks in third-party consoles + a smoke test against `nuprop.fly.dev`.
