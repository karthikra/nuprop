# Spec — S2: Manual Context UI on Client Detail page

**Date:** 2026-05-16
**Slice:** S2 of S0–S6 M16-M20 finish-line (see [audit](../audits/2026-05-16-m16-m20-state-audit.md))
**Depends on:** S1 backend hardening (commit `81833fb` on `main`)
**Worktree:** `m16-m20-s2-context-ui`
**Owner:** Karthik
**Estimate:** 1 day
**Status:** spec — awaiting approval

---

## Goal

Make M16 end-to-end usable. Today the only way to attach manual context to a client is via the chat `ContextCheck` component, and only on a new proposal with no chat history. After S2, the agency owner can paste context (emails, meeting notes, etc.) directly on the Client Detail page, preview the LLM extraction before committing, and see the natural-language brief that proposals will receive — turning the Client Detail page into the persistent, reusable home for client context.

S1 hardened the backend; S2 closes the UI loop for the manual-context half of M16. Connector context (Gmail/Drive/Cal/Slack) is S3's surface; pipeline integration of context_brief into the remaining 6 phases is S5's.

---

## What "shipped" looks like

After S2 merges to `main`, all of the following are true:

1. **Inline context paste flow on Client Detail page.** A collapsible "✨ Add or update context" section opens to a textarea + "Extract preview" button. The user pastes raw text, sees the structured extraction, then clicks "Save to client" to merge it (or "Edit text" to revise, or "Cancel" to discard).
2. **Trust loop closed.** The preview shows the same fields that the existing read-only `ContextProfileCard` displays (relationship, pricing_intelligence, past_work, risks, opportunities), so the user can visually compare "what I'm about to commit" with "what's already there".
3. **Context brief preview.** The existing `ContextProfileCard` gains a "Show what the AI sees" toggle that calls `GET /clients/{id}/context-brief` on-demand and renders the natural-language brief that proposal generation will receive.
4. **Reset destruction.** The card also gains a low-contrast "Reset context" button that wipes `context_profile` via `PATCH /clients/{id}` with `context_profile: {}` after a native `confirm()`.
5. **Backend additions.** Two new endpoints: `POST /clients/{id}/context/preview` (extract only, no persist) and `POST /clients/{id}/context/save` (merge a pre-extracted profile). The existing `POST /clients/{id}/context` (extract + save in one call) stays for backwards compat with the chat `ContextCheck` component.
6. **Tests cover each fix.** Three new vitest files + two new pytest cases. Backend stays ≥291 passing; frontend reaches ≥139 passing across 25+ files.
7. **No regression to existing surfaces.** The chat `ContextCheck` flow keeps working unchanged. Client Detail's existing Intelligence cards (sentiment timeline, source breakdown, preference overrides) keep working unchanged.

### Explicit non-goals for S2

- Migrating the chat `ContextCheck` component to the new preview-then-save flow (noted as follow-up in S6).
- Field-level inline editing on the `ContextProfileCard` (e.g., tweaking individual `past_work` rows). Deferred.
- Email enrichment of the brief preview (`?include_emails=true`) — requires S3's connector frontend to be useful.
- Touching the chat-side context UI styling.
- Extracting `QualityBadge` or the three Intelligence cards from `detail.tsx`. Only `ContextProfileCard` gets extracted (because S2 modifies it).

---

## Architecture decisions

### D1 — Two new backend endpoints, not one with a `save: bool` param

**Change:** Add `POST /clients/{id}/context/preview` and `POST /clients/{id}/context/save`. The existing `POST /clients/{id}/context` stays.

- `/preview` — body `{raw_text: str}`. Calls `ctx.extract_context(raw_text)` and returns the resulting structure as-is. No DB write, no merge.
- `/save` — body `{profile: dict}` (the structure the client just received from `/preview`). Calls `ctx.merge_context(existing, profile)` and persists. No LLM call.

**Why:** Two distinct HTTP verbs map cleanly to two distinct user intents ("show me what you'd extract" vs "commit this"). A `save: bool` param would mix verbs and force every endpoint test to enumerate combinations. Both new endpoints take `ctx: ContextService = Depends(get_context_service)` so test overrides apply per S1's pattern.

**Test surface:** `test_clients_context_preview.py` (new) — preview returns structure without persisting. `test_clients_context_save.py` (new) — save merges a structure into an existing profile.

### D2 — Inline expanding section, not modal/drawer/dedicated route

**Change:** New component `<AddContextSection clientId>` rendered on `detail.tsx` between the Contacts card and the `ContextProfileCard`. Collapsed by default; click expands to textarea → expand to preview → save/edit/cancel.

**Why:** Matches the existing card-grid pattern on the page (no overlay machinery). Easier to test (no portals/focus traps). The user can scroll up to reference the existing context while pasting.

**Test surface:** `add-context-section.test.tsx` — paste→preview→save (happy), paste→preview→edit→re-preview, extract error, save error.

### D3 — Extract `ContextProfileCard` only; leave `QualityBadge` and Intelligence cards inline

**Change:** Move the existing `ContextProfileCard` function out of `detail.tsx` into `frontend/src/components/clients/context-profile-card.tsx`. Add a `clientId` prop (needed for the new brief toggle + reset button). Add the brief-toggle and reset-button slots.

**Why:** S2 only modifies `ContextProfileCard`. Extracting `QualityBadge` or the three Intelligence cards would be scope creep (none of them changes). The current `detail.tsx` is at 250 LOC; extracting one component plus adding `<AddContextSection>` keeps it readable without a wholesale rewrite.

**Test surface:** `context-profile-card.test.tsx` — renders profile, reset button shows `window.confirm` (mocked) and calls API, brief toggle expands.

### D4 — Preview state machine lives in `<AddContextSection>`, not in a global store

**Change:** The five UI states (`collapsed | textarea | extracting | preview | saving`) are local component state, plus the pasted text and the previewed structure. No Zustand changes.

**Why:** Only one Client Detail page is mounted at a time, no need for global state. Component state is easier to test with RTL.

### D5 — Brief preview is on-demand, not always-rendered

**Change:** `<ContextBriefToggle clientId>` uses TanStack Query with `enabled: isOpen`. Closed = no fetch. Opened = one fetch. Cached for the page lifetime via the existing default query cache. Closed-then-reopened = serves from cache (no second LLM call).

**Why:** The brief endpoint calls Claude Sonnet (~3s + cost). Always-render would make page load slow + expensive. On-demand puts cost behind explicit user intent.

**Test surface:** `context-brief-toggle.test.tsx` — closed = no API call, opened = one call, closed-then-reopened = still one call.

### D6 — Reset uses native `confirm()`, not a custom modal

**Change:** Reset button onClick handler: `if (!confirm('Reset all context for ${client.name}? This cannot be undone.')) return; resetContext.mutate(client.id)`.

**Why:** Matches existing pattern (the Delete client button at `detail.tsx:25` already uses `confirm()`). Browser-native, accessible, zero new components. The destructive action is rare and recoverable (user can re-paste).

### D7 — MSW handlers per-test file

**Change:** Each new test file sets up its own MSW server with handlers specific to that test. No shared mock fixtures.

**Why:** Matches existing pattern (e.g., `frontend/src/components/chat/__tests__/preference-panel.test.tsx`). Per-test handlers make request expectations obvious at the test site. No shared mutable state.

---

## File-by-file change list

**Backend (new):**

- `backend/app/views/v1/clients.py` — add `POST /clients/{client_id}/context/preview` and `POST /clients/{client_id}/context/save` route handlers (both take `ctx: ContextService = Depends(get_context_service)`)
- `backend/app/domain/schemas/client_schemas.py` — add `ContextPreviewResponse` (returns `extracted: dict`) and `ContextSaveRequest` (takes `profile: dict`)
- `backend/tests/integration/test_clients_context_preview.py` — new
- `backend/tests/integration/test_clients_context_save.py` — new

**Frontend (new):**

- `frontend/src/components/clients/context-profile-card.tsx` — extracted from `detail.tsx`, plus `<ContextBriefToggle>` slot + reset button
- `frontend/src/components/clients/context-brief-toggle.tsx` — on-demand fetch + render
- `frontend/src/components/clients/add-context-section.tsx` — the inline state machine
- `frontend/src/components/clients/__tests__/context-profile-card.test.tsx` — new
- `frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx` — new
- `frontend/src/components/clients/__tests__/add-context-section.test.tsx` — new

**Frontend (modified):**

- `frontend/src/api/clients.ts` — add `useContextPreview()` (calls `POST /context/preview`), `useContextSave()` (calls `POST /context/save`), `useContextBrief()` (calls `GET /context-brief`), and `useResetContext()` (thin wrapper around the existing `PATCH /clients/{id}` with `context_profile: {}` — no new HTTP endpoint, just a named convenience hook that invalidates the right query keys)
- `frontend/src/pages/clients/detail.tsx` — import the extracted `ContextProfileCard` from its new path; render `<AddContextSection />` between Contacts card and Context card; remove the inline `ContextProfileCard` function definition

**Total:** 2 new app files (backend routes + schemas modify existing), 3 new component files, 3 new component test files, 2 new pytest files, 2 modified files (`api/clients.ts`, `pages/clients/detail.tsx`).

---

## Open questions for review

**Q1 — Should `POST /context/save` validate the `profile` shape against the extraction schema?**

Recommended: **no, trust client roundtrip.** The profile came from `/preview` which the server itself produced — re-validating would be defensive coding against a class of bug that doesn't exist in practice. If a future caller crafts a malformed profile, `merge_context` already handles missing keys gracefully (it falls back to `.get(...)` calls). Note as low-risk for S6 if it ever becomes a problem.

**Q2 — Should the preview-response cache live in React Query or in component state?**

Recommended: **component state.** The preview is a one-shot per session — the user pastes, previews, saves. No reuse value. React Query would mean every paste keys a new cache entry that never gets reused.

**Q3 — Should `useContextBrief` carry `include_emails` as a parameter today even though it's always `false` in S2?**

Recommended: **no, hardcode `false` in S2.** Adding the param now invites a half-built feature. S3 (connector frontend) can add the toggle when there are emails to enrich with.

**Q4 — Should we surface "context updated at" timestamp anywhere?**

Recommended: **no, defer.** The backend doesn't track a per-`context_profile` timestamp today (only `Client.updated_at` which moves for any client edit). Adding one is its own slice.

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Extracted preview structure differs subtly from the structure `merge_context` expects on save (because we passed it through JSON instead of in-process) | Low | The schema is a `dict` on both ends; JSON round-trip preserves all field types we care about (str, int, list, dict). Test `test_context_preview_then_save_roundtrips` covers it. |
| User opens brief toggle, closes the page, reopens — gets stale brief from before their `/save` invalidated the underlying profile | Medium | `useContextSave.onSuccess` invalidates the `['clients', id, 'context-brief']` query key. Tested. |
| `<AddContextSection>` keeps the textarea content when user clicks "Edit text" but loses it on "Cancel" | Intentional | Documented in component code: "Edit text" preserves state; "Cancel" clears it. |
| Extracting `ContextProfileCard` breaks an existing snapshot test | Low | No snapshot tests exist for `detail.tsx`. Verified via grep. |
| Reset button fires before `useResetContext` mutation completes, leaving UI desync'd | Low | Disable the button during `mutation.isPending`. Standard TanStack pattern. |

---

## Acceptance test checklist (post-implementation)

- [ ] `cd backend && .venv/bin/python -m pytest -q` → 289 baseline + 2 new preview/save tests = ≥291 passing. No skipped.
- [ ] `cd frontend && pnpm test --run` → 131 baseline + ≥8 new tests across 3 new files ≈ 139+ passing across 27 files.
- [ ] Manual smoke: open a fresh client in `pnpm dev`, paste a sample email, click "Extract preview", verify structured fields render, click "Save to client", verify `ContextProfileCard` updates without page reload.
- [ ] Manual smoke: click "Show what the AI sees" on a populated `ContextProfileCard`, verify natural-language brief renders. Close, re-open — verify no second network call (DevTools).
- [ ] Manual smoke: click "Reset context", confirm in the native dialog, verify `ContextProfileCard` disappears (empty profile case).
- [ ] `grep -n "from app.services.context_service" backend/app/views/v1/clients.py` returns zero results — confirms the inline `ContextService()` instantiation is fully gone (S1 already did this for the two existing routes; the two new routes must follow suit).

---

## What lands next (S3 preview)

After S2 merges and approval: open worktree `m16-m20-s3-connector-frontend`, write spec for the Drive/Calendar/Slack React Query hooks + Slack OAuth callback route + sync UI + tests. Aims to be 1.5 days.
