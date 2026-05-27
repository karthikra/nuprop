# NUPROP Session Handoff

**Last updated:** 2026-05-27 (S10 image media shipped)
**Latest commit on `main`:** `<merge commit>` (S10 merge). Pushed; auto-deploy run triggered.
**Working tree:** clean. On `main`. In sync with `origin/main`.
**Production:** **LIVE at https://nuprop.fly.dev** — health 200, all 13 secrets deployed. Live features: rate-card wizard (onboarding step 2), Gmail client discovery (`/clients`), and as of this session the proposal pipeline now consumes client context (S5 — backend, not directly visible in the UI).

**M16-M20 roadmap status:** S1–S7 COMPLETE. All M16-M20 work — backend + frontend — is fully shipped.
**Post-roadmap slices:** S8 (smart rate card) COMPLETE — see "What happened this session" below.
S9 (section schema + two-pass generation + editor) COMPLETE — see "What happened this session" below.
S10 (image media — upload + Nano Banana generation) COMPLETE — see "What happened this session" below.

---

## 🛑 START HERE NEXT SESSION

The work is shipped; what's pending is **verification + cleanup**, all requiring you in a browser or OAuth console — none of it can be automated. Do it in this order.

### 1. Smoke tests — three features shipped to prod, none ever clicked

Open https://nuprop.fly.dev → register (use `karthik.ramesh@veeville.com` or any `@example.com` — NOT a `.local` email, Pydantic rejects it).

**1a. Rate-card wizard** (onboarding step 2, hit right after registration): walk the 4 sub-steps — Offerings (2a) / Hourly Rates (2b) / Multipliers (2c) / Globals (2d). Every "Skip this section" advances; on 2d "Skip" submits like Finish. Add at least one offering and a couple of hourly rates so later phases have a rate card to work with.

**1b. S4 P6 — OAuth connectors** (Settings page):

| # | Action | Expected |
|---|---|---|
| 1 | **Connect Gmail** | Popup → accounts.google.com → Allow → `/settings/gmail-callback` → "Gmail connected" → green badge + your address |
| 2 | **Connect Slack** | Popup → slack.com/oauth/v2/authorize → Allow → `/settings/slack-callback` → "Slack connected" → workspace name |
| 3 | **Drive** card → Sync Now | ~5s → green "Found X documents across Y clients" |
| 4 | **Calendar** card → Sync Now | ~5s → green "Found X meetings across Y clients" |
| 5 | **Gmail** card → Sync Now | ~15s → success alert. ⚠️ "0 emails" is EXPECTED if you have no clients yet — Gmail sync searches BY client domain (see "Gmail sync needs clients" gotcha below). Step 1c fixes this. |
| 6 | **Slack** card → Sync | ~10s → green "Found X mentions across Y clients" |

**1c. Client discovery from Gmail** (`/clients`, needs Gmail connected):

| Action | Expected |
|---|---|
| `/clients` with 0 clients + Gmail connected | Empty state: "Add a client manually" + "Discover from Gmail" |
| **Discover from Gmail** | Modal "Look back how far?" → 30/90/365 buttons (90 highlighted) |
| Pick a window | "Scanning your inbox…" (~3-20s) → candidate list |
| Candidate list | Checkbox rows: name guess, domain, email count, sender count, date range. Noise filtered (freemail, github/linear/etc., no-reply, your own `veeville.com`) |
| Tick candidates → **Review N selected** | Sequential wizard, pre-filled ClientForm per candidate (name = domain guess, contacts = top senders) |
| After last candidate | "Created N clients" → Done → `/clients` refreshes |

Then re-run **Gmail Sync Now** (step 5) — now that clients exist, it should find real emails instead of "0 emails".

**1d. S5 spot-check (optional, backend behavior).** S5 has no new UI. To eyeball it: create a client, add some context to its profile (the `/clients/:id` context section, or run a connector sync that populates the profile), then create a proposal for that client and run it through. The covering letter / research should reference the relationship. Also: after a Gmail sync, a background `enrich_context_from_emails` ARQ job runs — check `fly logs -a nuprop | grep -iE "enrich"` for `connector.enrich.client_done` events.

Debugging any of the above: `fly logs -a nuprop | grep -iE "connector|oauth|discovery|enrich|encrypt" | tail -30`

Common gotchas: allow popups for `nuprop.fly.dev`; Google `redirect_uri_mismatch` → the redirect URI must be exactly `https://nuprop.fly.dev/settings/gmail-callback`; Slack "Invalid OAuth state" → 10-min nonce expired, click Connect again; Drive/Cal "Google not connected" → do Gmail first.

### 2. Rotate secrets (chat-exposure cleanup) — after smoke tests pass

Three secrets were pasted into AI chat transcripts during S4 and should be rotated:
- `GOOGLE_CLIENT_SECRET=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`
- `SLACK_CLIENT_SECRET=fdf51ff06cedda29a2f0c27cd1f59415`
- `ENCRYPTION_KEY=t6TjRRsjv8rqhpDf2M-kRFnhw9MGuVx9wBCu5vIYeIk=`

Steps:
1. **Google:** https://console.cloud.google.com/apis/credentials → NUPROP Web Client → **Add secret** (don't reset — keep old enabled until the redeploy confirms).
2. **Slack:** https://api.slack.com/apps → NUPROP → Basic Information → App Credentials → **Regenerate**.
3. **Fernet:** `backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`
4. **Atomic push** (ONE command — S1 lifespan refuses to start if OAuth creds are set without ENCRYPTION_KEY):
   ```bash
   fly secrets set -a nuprop \
     GOOGLE_CLIENT_SECRET="<new>" \
     SLACK_CLIENT_SECRET="<new>" \
     ENCRYPTION_KEY="<new fernet>"
   ```
5. ⚠️ Rotating ENCRYPTION_KEY invalidates ALL stored Gmail + Slack tokens (the vault encrypts both). After rotation, **disconnect** then **reconnect** Gmail + Slack in Settings.
6. Disable the old Google client secret once re-auth works.

### 3. Worktree / branch cleanup (~1 min)

Check for leftover worktrees from this session: `git worktree list`. If `s5-pipeline-integration` is still listed, remove it: `git worktree remove --force .claude/worktrees/s5-pipeline-integration` then `git worktree prune`, and `git branch -d worktree-s5-pipeline-integration` (it's merged). (As of this handoff the worktree was already cleaned up — verify.)

### 4. Pick the next slice

- **S7 — frontend follow-ups** (~0.5d): ContextBriefToggle cache survives invalidation (S2 follow-up); `getAuthUrl.isError` / `disconnectSlack.isError` surfacing in connector cards (S3 follow-up); rate-card wizard's timed yellow skip-notice. Needs a fresh brainstorm → spec → plan cycle.
- **`sync_emails` is fine** — its 401→400 fix already shipped 2026-05-21.
- **`pricing_model`** — S5 carries it in the merged config but `CostModelBuilder` doesn't branch on it (no alternative pricing path exists). If you want it to actually do something, that's a fresh design conversation: *what is the alternative pricing model?*
- Other future-work items are listed in each slice's spec under "Future work".

---

## What happened this session (2026-05-27 — S10)

Shipped **S10 — image media (upload + Nano Banana generation)**, the second slice of the S9-S13 section-redesign roadmap.

### Architecture

- **S3 bucket `nuprop-proposal-assets`** in `ap-northeast-1` — private, block-public-access on, CORS allows PUT/GET/HEAD from `https://nuprop.fly.dev` and `http://localhost:5173`, single tag-filtered lifecycle rule (`published=false` → expire 90d). Provisioned via `backend/scripts/bootstrap_s3.sh` (idempotent shell — no IaC anywhere else in the repo). **Note:** S10 doesn't yet stamp the `published=false` tag on uploads, so the rule no-ops until S12 wires tag-on-upload into commit/generate. Safe default for the pre-published-prod state.
- **New media service package** at `backend/app/services/media/`: `_common.py` (kinds, mime/size caps, `Asset` TypedDict, key shape with regex-validated inputs as defence against path-traversal), `_s3.py` (cached boto3 client; presigned PUT 15min / GET 1h; async-offloaded upload/delete), `_fal.py` (async fal.ai wrapper — lazy import so test seam doesn't load `fal_client`), `image_gen.py` (Nano Banana → httpx download → S3 upload → `Asset`), `section_assets.py` (pure helpers: append/remove/resign — never mutates input).
- **Four section-scoped asset endpoints** under `/api/v1/proposals/{id}/sections/{type}/assets/...`:
  - `presign` — `{kind, filename, content_type, size}` → `{upload_url, s3_key, asset_id}`. Validates via `validate_upload`; 400 on oversize/wrong-mime/unknown-section.
  - `commit` — records the just-uploaded asset on the section. **Three defence-in-depth checks**: `s3_key` prefix must equal `{agency_id}/{proposal_id}/` (closes IDOR via crafted key); `kind`/`content_type` must be consistent; `s3_key` extension must match `content_type`.
  - `generate` — `kind=image` only in S10 (400 for video/audio; S11 widens). `RuntimeError` from fal.ai is translated to **502** (clean UX for content-policy blocks).
  - `delete` — DB update + commit BEFORE S3 delete (DB is source of truth; orphan S3 objects are swept by the lifecycle rule once S12 enables tagging).
- **Re-sign on read.** `_resign_response_sections` mutates the Pydantic `ProposalResponse` (NEVER the SA model — `get_db` commits on session exit, so mutating the row would persist the transient URL). Wired into `GET /proposals/{id}` and `PATCH /proposals/{id}`.
- **Frontend:** new `AssetRow` (thumbnail grid + delete) and `AddImageMenu` (split-button: Upload file / Generate with AI) live under each `SectionBlock`, gated on `included=true`. Uploads go presign → bare `axios.put` direct to S3 (bypasses the wrapped api client's auth interceptor — S3 rejects `Authorization` headers) → commit. No bytes pass through Python on the upload path.

### Test counts

- Backend: `406 → 463` (+11 media-common base + 13 media-common hardening, +7 section-assets, +4 image-gen, +12 asset endpoints initial + 5 review follow-ups, +1 re-sign-on-GET, +5 final-review fixes: 2 regen/refine asset-preserve regressions + 1 transient-url-not-persisted + 2 kind=image-only enforcement).
- Frontend: `265 → 275` (+5 asset-row, +3 add-image-menu, +2 section-block integration).
- Migration head: `05_proposal_section_columns` (no schema change in S10).

### Non-goals carried forward to S11+

- Video + audio kinds — S11 widens `/assets/generate` and adds `+ Add video` / `+ Add audio` menus.
- Video first-frame poster — optional in S11 spec.
- `published=true` tagging on Publish (and the matching `published=false` tag-on-upload) — S12. Until then, lifecycle rule no-ops, assets stay forever.
- NUSTAGE pull via `GET /export?token=…` — S12.

### Known follow-ups (out of S10 scope)

- **Lost-update race on the section JSON column.** Read-modify-write pattern in `commit_asset`/`generate_asset`/`delete_asset` (and pre-existing `patch_section`) is non-atomic. Two concurrent writes silently lose one. Fix candidates: optimistic concurrency via `updated_at`, `SELECT ... FOR UPDATE`, or Postgres `jsonb_set + ||` atomic append. Defer to a follow-up; affects S9 surface too.
- **`AddImageMenu` dropdown click-outside-to-close** missing — open menu stays open until a choice is made.
- **`URL.createObjectURL` revoke** is now wired in `readImageDimensions`, but the broader Upload flow doesn't revoke the original `file` reference if the upload errors after presign.

### Operator steps needed before merge

1. **Provision the bucket:** `AWS_PROFILE=nuprop bash backend/scripts/bootstrap_s3.sh` (idempotent; head-check first). Run from a workstation with IAM creds that can `s3:CreateBucket`, `s3:PutBucketCors`, `s3:PutBucketPublicAccessBlock`, `s3:PutLifecycleConfiguration`.
2. **Push `FAL_KEY` to Fly:** `fly secrets set -a nuprop FAL_KEY="<key>"`. Get the key from https://fal.ai/dashboard. The app boots without it but `/generate` will 502 until the secret is set.
3. **Verify the bucket region matches `AWS_REGION` (`ap-northeast-1`)** — Fly's app pool needs IAM creds with `s3:PutObject` / `s3:GetObject` / `s3:DeleteObject` on `arn:aws:s3:::nuprop-proposal-assets/*`. If not, attach a minimal policy.

---

## What happened this session (2026-05-26 — S9)

Shipped **S9 — section schema + two-pass LLM generation + long-form editor**, the first slice of the S9–S13 section-redesign roadmap.

### Architecture

- **Schema:** 7 legacy text columns dropped (`covering_letter`, `covering_letter_alt`, `executive_summary`-as-Text, `scope_sections`, `cost_rationale`, `terms`, `email_draft`); 9 new JSON columns added — one per canonical section type. Each column carries `{content, assets, included, metadata}`. Migration `05_proposal_section_columns`.
- **Two-pass generation:** `PipelineService.generate_sections` replaces the old `generate_narrative` and `generate_outputs` phases. Pass 1 runs 7 fact generators in parallel via `asyncio.gather`; Pass 2 runs 2 synthesis generators sequentially with Pass-1 outputs in the prompt. All section generators live in `app/services/ai/section_facts.py` and `section_synthesis.py`.
- **Approval flow:** the narrative gate is removed. Cost-model approval enqueues `generate_sections` directly. After generation completes the pipeline transitions to `section_editor` and the frontend surfaces the editor.
- **Section CRUD:** `PATCH /proposals/{id}/sections/{type}` (content / included / metadata), `POST /sections/{type}/regenerate` (fresh LLM variant), `POST /sections/{type}/refine` (instruction-steered rewrite).
- **Frontend:** new `components/sections/section-editor.tsx` renders included sections in canonical order. Each section is a `section-block.tsx` with auto-save (1s debounce), regenerate, refine-with-prompt, and toggle-off. No media yet (S10 unlocks images, S11 unlocks video + audio). The narrative-preview chat card was removed.

### Test counts

- Backend: 376 → **~406** (+~30 across section helpers, fact/synthesis generators, the `generate_sections` phase, the cost-model gate change, the section CRUD endpoints, plus updated legacy tests).
- Frontend: 260 → **265** (+5 for the section-block component).
- Migration head: `05_proposal_section_columns`.

### Non-goals carried forward to S10–S13

- Media (image / video / audio): S10 + S11.
- NUSTAGE export + share token + Publish: S12.
- Context UX (persistent chip + Gmail picker): S13.
- CTA / Appendices section types: deferred entirely.
- DOCX / PDF: removed in S9; returns as downloadable artifacts in S12.

### Notable cleanup also landed

- `app/services/ideation_service.py` updated to read from the new section dicts (`cover_page`, `executive_summary`) instead of the dropped legacy text columns — required to keep the ideation side-channel functional after the schema migration.

---

## What happened this session (2026-05-24 — S8)

Shipped **S8 — smart rate card**: rate-card gaps are detected the moment the brief is analysed, surface as a chat fill-card after the template gate, and can be resolved three ways — manual fill (additive to the agency rate card), Excel import (per-proposal override), or skip (use estimated defaults).

### Architecture

- **Gap detection (backend).** New `services/ai/rate_gap_analyzer.py`. `PipelineService.analyze_brief` calls it post-commit and writes `proposal.rate_card_gaps` if the agency's active rate card is missing any needed entries.
- **Pause point (backend).** `ChatViewModel.approve_gate("template", ...)` short-circuits if `rate_card_gaps` is set — `run_research` is NOT enqueued until the gaps are cleared.
- **Resume paths (backend).** Three endpoints under `/proposals/{id}/rate-card-gaps`: `/fill` (merges into agency master), `/skip` (clears without modifying), and the `/rate-card-import` + `/rate-card-import/confirm` pair (writes per-proposal override). All three enqueue `run_research`.
- **Cost-model precedence (backend).** `CostModelBuilder.build` now consults override → agency → fallback in that order and stamps `cost_model.source` so the frontend can show which one was used. (Note: the builder signature was refactored away from `db`/`agency_id` parameters — the pipeline now resolves the active rate card via `RateCardRepository.get_active` before calling build.)
- **Excel parsing (backend).** New `services/rate_card_excel_parser.py` uses `openpyxl` for the read and `AIService.complete_json` for the structured extraction. Empty rows are stripped before the LLM call; a warning fires when the prompt exceeds 50k chars; the confirm body is validated by a `RateCardConfirmBody` Pydantic schema.
- **Chat fill-card (frontend).** New `components/chat/rate-gap-card.tsx` renders when `proposal.rate_card_gaps != null`. Three actions in one card: manual fill (with field-level validation and a disabled submit until all fields are positive integers), Excel drop with surfaced upload errors, and skip. Confirm dismisses the preview on success via the corrected `['proposals', proposalId]` query-key invalidation.

### Schema

Migration `04_proposal_rate_card_columns` adds two nullable JSON columns to `proposals`: `rate_card_gaps` and `rate_card_override`. No backfill.

### Test counts

- Backend: 359 → **375** (+16 across gap-analyzer, integration, endpoints, override, import)
- Frontend: 256 → **260** (+4 for the rate-gap-card)

### Non-goals (deferred)

- Multi-dimensional rate cards (per-client / per-job overrides at the agency master level).
- Editing existing rate-card entries from the chat — fill only ever ADDS.
- `.csv` / `.xls` / Google Sheets import (only `.xlsx` for now).
- Multi-currency rates.
- Saving an imported override back to the agency master.

### Known follow-ups

- `_no_network` autouse fixture in `tests/conftest.py` only blocks the `AnthropicClient` facade methods, not `AIService.complete_json` directly. The S8 analyzer + Excel parser are failure-safe so this isn't a real test-flake risk today, but a future direct `AIService` caller without a try/except wouldn't be caught.
- The `rate-gap-card`'s preview is rendered as raw JSON via `<pre>JSON.stringify(...)</pre>`. Acceptable for v1; a polished preview with `low_confidence_fields` badges would be a UX win.
- The agency-master `RateCardViewModel.add_missing_entries` auto-creates a fresh rate card with `version="v1"` if no active one exists. If an agency has multiple historical rate cards, this is the right default; if a deeper version-bump policy is needed, that's a separate slice.

---

## What happened this session (2026-05-23 — S7)

Shipped **S7 — frontend follow-ups**, the final M16-M20 slice. Three small UX gaps deferred from S2/S3/rate-card wizard, plus a piece of test-infrastructure work that surfaced during the rate-card-wizard tests:

- **ContextBriefToggle refetches after invalidation.** The local `cached` state was dropped in favor of React Query's own cache with `staleTime: 5 * 60 * 1000` and `gcTime: 5 * 60 * 1000` set on the query (the per-query `gcTime` overrides the test QueryClient's `gcTime: 0` default). After `useContextSave` / `useResetContext` invalidates the brief query, the next open of the toggle refetches automatically.
- **Gmail and Slack connector cards surface connect + disconnect errors.** Both cards now render an inline red `formatApiError` block when `getAuthUrl` or `disconnect` mutations fail. Drive and Calendar cards have no OAuth/disconnect flow and were left untouched. Both `handleConnect` functions wrap `mutateAsync` in a try/catch so the rejection doesn't surface as an unhandled promise rejection in the test runner.
- **Rate-card wizard skip-notice wired.** `WizardShell.notice` was always there; `RateCardWizard` now populates it: clicking "Skip this section" on an intermediate step shows "You can fill this in later in Settings." for 5 seconds. The timer is cleared on unmount and on consecutive skips so it never stacks. Last-step skip still submits and shows no notice.
- **Test infrastructure compatibility patch.** `src/test/setup.ts` overrides `@testing-library/react`'s `asyncWrapper` to detect vitest fake timers (the default only checks `typeof jest`, which vitest never sets), and wraps `vi.advanceTimersByTime` in `React.act()` so React 19 concurrent-mode state updates from fired timer callbacks flush synchronously. The TODO comment in that file documents the removal condition (when `@testing-library/dom >= 11` ships vitest-aware fake-timer detection).

### Commits (on branch `worktree-s7-frontend-followups`)

- Task 1 (`1ea56d8`) — ContextBriefToggle drops local cache, useContextBrief gains staleTime/gcTime.
- Task 2 (`1b39ce1`) — Gmail card surfaces getAuthUrl + disconnect errors.
- Task 2 fix (`ca6d4c1`) — both cards' handleConnect wraps mutateAsync in try/catch.
- Task 3 (`034e78f`) — Slack card surfaces getAuthUrl + disconnect errors.
- Task 4 (`93671a5`) — Rate-card wizard skip-notice wiring.
- Task 4 test infra (`b705ca9`, `876e8eb`) — vitest+React 19 fake-timer compatibility patch.

### Test counts

- Frontend: **255 passing** (was 247 — +8 S7 tests)
- Backend: 359 passing (unchanged — S7 is frontend-only)
- Migration head: `03_proposal_context_brief` (no schema change)

S7 is the last roadmap slice. M16-M20 is done.

---

## What happened this session (2026-05-23)

Shipped **S6 — connector resilience & backend hardening**, the last roadmap slice. Brainstorm → spec → 10-task plan → subagent-driven execution → final regression.

S6 makes the four connector HTTP clients resilient to transient provider failures and closes the remaining audit-flagged HIGH backend hardening items.

### Commits (on branch `worktree-s6-connector-resilience`)

- S6 spec + plan: `ab24989` (spec), `fdf8bdf` (spec amendment), `4202a91` (plan)
- Task 1 — retry wrapper: `fca15e2`, `5ed05e8` (review fixes: -O-safe exhaustion guard, Retry-After cap, transport-exhaustion test)
- Task 2 — gmail_client migration: `c18d403`, `294f129` (revoke_token max_attempts=1)
- Task 3 — Drive/Cal/Slack migration: `517367c`, `730d264` (OAuth exchange_code max_attempts=1, test polish)
- Task 4 — gmail pagination cap: `aedf593`
- Task 5 — gmail bad-date returns None: `92f403a`
- Task 6 — `_extract_domains` @ guard: `76c64b3`
- Task 7 — LLM call timeout: `57608b4`
- Task 8 — client_repo cap raise: `e630e2e`

### Test counts

- Backend: **355 passing** (was 339 — +16 S6 tests)
- Frontend: 247 passing (unchanged — S6 is backend-only)
- Migration head: `03_proposal_context_brief` (no schema change in S6)

### Architecture: S6 at a glance

```
Two pieces —

A. Shared retry/backoff wrapper
   New module: app/infrastructure/external/_retry.py
   exposing request_with_retry(method, url, *, timeout=30.0,
   max_attempts=4, transport=None, **kwargs) -> httpx.Response.
   Retries 429/5xx and httpx.TransportError; never retries other 4xx
   (a 401 invalid_grant must surface). Honors Retry-After (capped at
   60s). Exponential backoff with jitter otherwise. -O-safe exhaustion
   guard. The single policy point — all four connector clients
   (gmail/gdrive/gcal/slack) route through it. OAuth code exchanges
   (gmail.exchange_code, slack.exchange_code) and gmail.revoke_token
   override max_attempts=1: authorization codes are single-use and
   revokes are best-effort; retrying either is pure latency cost.

B. Hardening fixes
   - gmail_client: MAX_PAGE_ITERATIONS=50 caps both pagination loops
     against the pathological "0 messages + non-null pageToken" loop.
   - gmail_client.get_message: unparseable Date header returns date=None
     instead of naive datetime.now(); the existing viewmodel coercion
     (msg["date"] if isinstance(msg["date"], datetime) else now) applies
     a tz-aware fallback at persist time. No schema change required.
   - connector_viewmodel._extract_domains: skips contacts whose email
     lacks an "@", matching the existing guard pattern in the file.
   - services/llm.py: LLM_TIMEOUT_SECONDS=120.0 passed to
     AsyncAnthropicBedrock so a hung Bedrock call can't stall a phase.
   - client_repo.search default limit 50 → 500.
```

### Lessons from this session

- The plan committed three small spec corrections against the real code before implementation began (line 259 was already @-guarded; the date fallback lives in gmail_client not the viewmodel; the LLM timeout belongs in AIService, not the AnthropicClient facade). S5's amend-and-flag lesson held.
- Two code-quality reviews caught the OAuth-code-exchange retry issue (Tasks 2 and 3): authorization codes are single-use (RFC 6749), so retrying after a 5xx wastes latency on a guaranteed failure. `max_attempts=1` is the right answer for any best-effort or single-use call.
- The pagination test used a `_SAFETY_BOUND = 200` to fail cleanly instead of hanging the suite when the cap is missing — a small TDD pattern worth remembering.

### Gotchas worth keeping

- **`raise_for_status` is inside the wrapper.** Don't call `r.raise_for_status()` again on the returned response — it's already raised before the wrapper returns to you.
- **`HTTPStatusError` and `TransportError` are both `httpx.HTTPError` subclasses.** Existing `except httpx.HTTPError` clauses in `gdrive.get_file_content_text` and `gmail.revoke_token` correctly catch everything the wrapper can raise.
- **Per-attempt `AsyncClient`.** The wrapper opens a fresh `httpx.AsyncClient` per attempt (matches the prior per-call pattern). Connection pooling is not preserved across the wrapper; this is intentional — a retry on a broken connection benefits from a fresh client.

---

## What happened this session (2026-05-22)

Shipped **S5 — pipeline integration**, the biggest semantic slice of the M16-M20 roadmap: brainstorm → spec → 10-task plan → subagent-driven execution → final review → `--no-ff` merge → push → deploy.

S5 makes the proposal pipeline actually USE the client context that S1-S4 collected. Before S5, of 7 pipeline phases only `run_research` consumed client context; the rest generated proposals as if the agency knew nothing about the client.

### Commits (on main, deployed)

```
f073dfe Merge: S5 pipeline integration            (--no-ff merge commit)
  └─ 12 S5 commits 1df9af9..5251ef9
5251ef9 fix(S5): stamp _sources[email] on context profile after enrichment
eb788c0 feat(S5): sync_emails enqueues enrich_context_from_emails after commit
…
1df9af9 feat(S5): add Proposal.context_brief column
feb2c1f fix(connector): sync_emails returns 400 not 401 for stale Gmail creds   (2026-05-21)
b0c7972 plan(S5)  /  90f75cb spec(S5)
```

### Test counts

- Backend: **339 passing** (was 325 — +14 S5 tests)
- Frontend: 247 passing (unchanged — S5 is backend-only)
- Migration head: `03_proposal_context_brief`

### Architecture: S5 at a glance

```
Three pieces —

A. Context-brief wiring
   New Proposal.context_brief TEXT column (migration 03).
   context_service.get_or_create_proposal_brief(session, proposal):
     returns proposal.context_brief if set; else generates via ContextService,
     persists to the column, commits. First phase pays one LLM call; rest read free.
   PipelineService._load_context_brief delegates to it.
   Wired into: analyze_brief, run_research (pre-existing), run_benchmarks,
     generate_narrative (covering letter), run_ideation.

B. Cost-model preferences
   build_cost_model now calls _merge_preferences_into_config(template_config,
     proposal.preferences) and passes the merged config to CostModelBuilder.
   discount_tags -> cost_model.default_multipliers (CostModelBuilder already
     consumes that). pricing_model is carried but NOT branched on (descope).

C. Post-sync email auto-enrichment
   New ARQ task: app/workers/enrichment.py :: enrich_context_from_emails
     (registered in WorkerSettings.functions).
   sync_emails, after committing email rows, collects clients that got new
     email and enqueues the job. The job feeds EmailIndex rows into
     ContextService.enrich_context_with_emails, writes the merged profile
     back, stamps _sources["email"] (mirrors Drive/Calendar/Slack).
   Terminal job — per-client errors isolated, never fails the sync.
```

### Lessons from this session

- The `backend/.venv` symlink that broke the *client-discovery* merge **did NOT recur** — the `.gitignore` hardening (dropped trailing slash: `.venv`, `node_modules`) correctly ignores symlinks now. Pre-merge verification (`git ls-files | grep .venv` → empty) confirmed it before merging.
- Subagent commit steps used explicit `git add <paths>` throughout — no `git add -A`. See `~/.claude/projects/.../memory/feedback_subagent_git_add.md`.
- Spec-vs-reality drift on `pricing_model`: the first exploration suggested `CostModelBuilder` had a pricing fork to select; the deeper read showed none. The plan header amended the spec's acceptance criterion rather than inventing pricing math. When a plan finds the spec over-promised, amend the plan and flag it — don't silently build the spec's literal words.

### Gotchas worth keeping

- **Gmail sync needs clients first.** `sync_emails` builds its Gmail query from existing client contact domains. An agency with 0 clients gets "0 emails" in 0 seconds — the Gmail API is never called. The client-discovery feature is the intended fix: populate clients, then sync finds their email.
- **Global 401 interceptor.** `frontend/src/api/client.ts` redirects to `/login` on ANY 401. Connector endpoints return **400** (not 401) for stale-Gmail-credential errors so they surface in-app instead of logging the user out. Both `discover_clients` and `sync_emails` already do this.
- **Pipeline phases are separate ARQ jobs** with separate DB sessions — anything shared between phases must be persisted (that's why `context_brief` is a column, not passed in memory).

---

## Quick verification (run first on resume)

```bash
cd /Users/karthikramesh/Developer/nuprop
git log --oneline -3            # HEAD = f073dfe
git status                      # clean, in sync with origin/main
git worktree list               # should be only the main checkout

cd backend && .venv/bin/python -m pytest -q     # → 339 passed
cd ../frontend && pnpm test                      # → 247 passed across 45 files

curl -s https://nuprop.fly.dev/api/v1/health     # → {"status":"ok","service":"nuprop"}
fly machines list -a nuprop                       # 3 machines
```

If `backend/.venv/bin/python` is missing (fresh clone): `cd backend && uv sync`.

---

## Where to look for what

| Thing | Path |
|---|---|
| **This file** | `docs/superpowers/HANDOFF.md` |
| S5 spec / plan | `docs/superpowers/specs/2026-05-21-s5-pipeline-integration-design.md`, `plans/2026-05-21-s5-pipeline-integration.md` |
| Client-discovery spec / plan | `docs/superpowers/specs/2026-05-19-*`, `plans/2026-05-19-*` |
| Rate-card wizard spec / plan | `docs/superpowers/specs/2026-05-18-*`, `plans/2026-05-18-*` |
| Prior specs/plans | `docs/superpowers/{specs,plans}/` |
| Project memory (auto-loaded) | `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/` |
| Pipeline phases | `backend/app/services/pipeline_service.py`, `backend/app/workers/pipeline.py` |
| **S5 new code** | `backend/app/workers/enrichment.py`, `get_or_create_proposal_brief` in `backend/app/services/context_service.py` |
| Backend tests | `backend/tests/{unit,integration}/` |
| Fly config | `fly.toml` (secrets via `fly secrets list -a nuprop`) |
| Auto-deploy workflow | `.github/workflows/deploy.yml` |

---

## How to resume next session

1. Read this file end-to-end (~3 min).
2. Run the "Quick verification" block above.
3. Pick from "START HERE":
   - **Smoke tests** (rate-card wizard + P6 OAuth + client discovery, ~20 min in browser) — three shipped features, none verified.
   - **Rotate secrets** (~10 min in OAuth consoles).
   - **S6 backend polish** — the last roadmap slice (deferrable; fresh brainstorm → spec → plan cycle).

Recommended order: smoke tests → secret rotation → decide on S6.
