# S7 — Frontend Follow-ups — Design

**Status:** Brainstormed 2026-05-23. Implementation plan: pending.
**Surfaces:** `frontend/` only — `ContextBriefToggle`, the Gmail/Slack connector cards, and the rate-card wizard's parent component. No backend changes, no API contract changes, no schema change.
**Slice:** S7 — the three frontend follow-ups deferred from S2 (manual context UI), S3 (connector frontend), and the rate-card wizard slice. Deferred during S6 as out-of-scope for the backend-only S6 work and tracked there for completion now.

---

## Goal

Three small UX gaps survived S2, S3, and the rate-card wizard slice. None is a correctness bug; together they're the difference between "shipped" and "polished". S7 closes them — frontend-only, vitest-only, ~0.5 day.

1. **ContextBriefToggle's local cache survives invalidation** — a user who saves or resets a client's context still sees the previous AI brief until the page is refreshed.
2. **Connector card error surfacing is partial** — a failed `getAuthUrl` or `disconnect` mutation on the Gmail and Slack cards is silent; only the `sync` mutations render errors.
3. **Rate-card wizard skip-notice is unwired** — `WizardShell` has a `notice` prop and renders an amber bar when set, but nothing ever sets it. A "Skip this section" click leaves the user with no acknowledgement.

## Non-goals

- No backend change. The API contract, query keys, and mutation endpoints are all untouched.
- No new design system component, no new styling primitive — we reuse the existing `formatApiError` helper and the amber-bar already rendered by `WizardShell`.
- No global "all mutations should surface errors" cleanup. We address the three call-outs and stop. Drive and Calendar cards have no OAuth/disconnect flow and stay untouched.
- No fix for the wider "manual context UI lives only on Client Detail" gap (still a future item from the audit, not in S7).
- No `pricing_model` design work, no client-list cursor pagination — those are tracked separately.

## Current state (from codebase exploration)

- `frontend/src/components/clients/context-brief-toggle.tsx:8-31` — the toggle keeps a local `cached` state and gates the underlying `useContextBrief` query with `enabled: open && cached === null`. Once `cached` is set after the first load, the query is permanently disabled for that component instance. When `useContextSave` (`api/clients.ts:101`) or `useResetContext` (`api/clients.ts:119`) invalidates `['client-context-brief', clientId]`, React Query marks the query stale — but with `enabled=false` there is nothing to refetch. The user sees the old brief until the component remounts. A code comment at `context-brief-toggle.tsx:14-18` already acknowledges this as a follow-up.
- `frontend/src/components/settings/slack-connector-card.tsx:92-96` — surfaces `syncSlack.isError` but not `getAuthUrl.isError` or `disconnectSlack.isError`. `useSlackDisconnect` is defined (`api/connectors.ts:165`) and `useSlackAuthUrl` exists; both mutations expose `isError` / `error` but neither is rendered.
- `frontend/src/components/settings/gmail-connector-card.tsx` — same gap. `useGmailAuthUrl` and `useGmailDisconnect` (`api/connectors.ts:29`, `:60`) are used but their `isError` paths are not rendered. (The card already renders the sync result; this slice adds the connect / disconnect failures.)
- `frontend/src/components/settings/drive-connector-card.tsx:37-38` and `calendar-connector-card.tsx:35-36` — already surface their sync errors; no OAuth/disconnect on these cards (they piggy-back on Gmail's Google token). Out of scope.
- `frontend/src/components/rate-card-wizard/wizard-shell.tsx:49-53` — renders a `notice` prop as an amber bar inside the wizard. The prop is wired through `Props` (`wizard-shell.tsx:13`).
- `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx:49-65` — constructs the `WizardShell` but never passes `notice`. The skip handler at line 55 (`onSkip={isLast ? handleContinue : advance}`) just advances silently.

## Architecture

### Piece A — Brief cache fix

Drop the local cache; let React Query own it.

- In `frontend/src/components/clients/context-brief-toggle.tsx`:
  - Remove the `cached` state and its `setCached` `useEffect`.
  - Remove the `useEffect` that resets `cached` on `clientId` change — irrelevant once the local state is gone.
  - Gate becomes `enabled: !!clientId && open`. `brief` is just `data` from the query.
- In `frontend/src/api/clients.ts` `useContextBrief`:
  - Add `staleTime: 5 * 60 * 1000` (5 minutes). Close+reopen within five minutes returns from React Query's in-memory cache with no refetch — preserving the original "instant close+reopen" goal. After five minutes (or after invalidation), the next open refetches automatically.

The "frozen-once-loaded" behavior the local cache was emulating becomes "fresh within `staleTime`, refetched on invalidation" — the React Query default semantics. The cross-mutation case (user resets context → reopens toggle) now refetches as expected.

### Piece B — Connector card error surfacing

For each missing isError path, render an inline red block mirroring the existing pattern at `slack-connector-card.tsx:92-96`:

```tsx
{getAuthUrl.isError ? (
  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
    {formatApiError(getAuthUrl.error, 'Slack connect failed')}
  </div>
) : null}
```

Coverage:

| Card | Mutations to surface |
|---|---|
| `slack-connector-card.tsx` | `getAuthUrl.isError`, `disconnectSlack.isError` |
| `gmail-connector-card.tsx` | `getAuthUrl.isError`, `disconnectGmail.isError` |

Placement: in each card, the new blocks go next to (or directly below) the existing button row for the relevant action. The exact spot is the implementer's call as long as the block is visible when the mutation errors. The styling (`rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700`) and the `formatApiError(error, '<fallback>')` shape stay identical to the existing sync error blocks.

### Piece C — Skip-notice wiring

In `frontend/src/components/rate-card-wizard/rate-card-wizard.tsx`:

- Add `notice: string | null` state, initialized `null`.
- Add a `useRef` (or module-scoped variable inside the component) to hold the active timer's ID so successive skips can cancel the prior timer instead of stacking.
- Define `handleSkip()` that calls the existing advance/submit logic AND, for intermediate skips only (i.e., `!isLast`), sets `notice = "You can fill this in later in Settings."` and schedules a `setTimeout(() => setNotice(null), 5000)`. The last step's skip path (`isLast ? handleContinue : advance`) goes through `handleContinue` which submits — that path must NOT show the notice (skipping the last step is a submit, not a defer).
- On unmount and on every fresh skip, clear any pending timer to prevent stale timeouts firing after the wizard has unmounted or after a subsequent skip.
- Pass `notice={notice}` to `WizardShell`.

The amber rendering at `wizard-shell.tsx:49-53` already handles display — we only wire the data.

## Error handling

- **Notice timer leak:** clear the timer on `useEffect` cleanup and at the start of every new skip. The dismissal must be cancelable so unmounting the wizard or skipping again doesn't leave an orphan `setState` call.
- **`enabled` regression on the toggle:** the existing `!!clientId` guard stays in the new `enabled: !!clientId && open` — without it a momentarily-empty `clientId` would hit `/clients//context-brief` and 404.
- **Missing mutation hooks:** if any of `useGmailAuthUrl` / `useGmailDisconnect` / `useSlackAuthUrl` / `useSlackDisconnect` were not exposing `isError` and `error`, the corresponding isError block would not compile. All four are defined and expose those fields today — verified.

## Testing

- **`context-brief-toggle.test.tsx`** — extend. New cases: (1) close+reopen within `staleTime` does not trigger a second fetch (assert the mocked `api.get` call count); (2) after `invalidateQueries(['client-context-brief', id])`, the next open does refetch.
- **`gmail-connector-card.test.tsx`** — extend (or create alongside the existing test files for the cards). New cases: a failed `getAuthUrl` mutation renders the inline red error; a failed `disconnectGmail` mutation renders the inline red error.
- **`slack-connector-card.test.tsx`** — same two new cases for `getAuthUrl` and `disconnectSlack`.
- **`rate-card-wizard.test.tsx`** — extend with three cases: (1) clicking "Skip this section" on an intermediate step sets the amber notice; (2) the notice disappears after 5 seconds (use `vi.useFakeTimers()`); (3) clicking "Skip this section" on the LAST step does NOT show the notice (it submits instead). One more: consecutive skips do not stack timers (advance, skip, advance, skip — only one timer pending).

Expected frontend test count: **247 → ~254**. Existing 247 must stay green; no backend test is touched.

## Future work

- Whole-app pattern for surfacing mutation errors consistently (not just on the connector cards).
- Manual context UI on the Client list page — still an audit gap unrelated to S7's three items.
- A reusable `<TimedNotice>` primitive if more wizards or forms grow timed acknowledgements. Premature to extract now.
