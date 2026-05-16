# NUPROP Session Handoff

**Last updated:** 2026-05-16 (end of working session)
**Latest commit on `main`:** `91bb135` (pushed to `origin/main`)
**Working tree:** modified — see "Loose ends" below. Branch: `main`. No active worktrees.

> Quick orientation: this doc gets you from a `/clear` to "ready to keep working" in under two minutes. The current state, the one queued workstream, the gotchas, and the exact next decisions are all below.

---

## TL;DR

NUPROP is a multi-tenant AI proposal copilot. Today's session executed the **Ideation side-channel** — a read-only Claude side-channel attached to each proposal, accessible via a drawer in the proposal page. 17-task plan from the 2026-05-15 session, executed via `superpowers:subagent-driven-development` (one implementer subagent per task + per-task spec & quality reviewers + a final cross-cutting reviewer). 16 of 17 tasks done; the remaining one is a manual docker smoke test.

What landed:
- Backend: new `chat_messages.channel` column + Alembic migration; `ChatMessageRepository` channel filter; `ChatMessageResponse.channel`; new `IdeationService.run_ideation` worker phase (Sonnet 4.6 with `cache_control: ephemeral` on the proposal-context system block); ARQ task wrapper with **isolated failure handling** (does NOT touch `pipeline_state` on error — writes a `system/error` chat row to the ideation channel + emits `pipeline_error` WS event); ViewModel + 2 new API routes under `/chat/{id}/ideation/*`.
- Frontend: `ChatMessage` type carries `channel`; chat store routes incoming WS messages into separate `messages` / `ideationMessages` slices (both `addMessage` AND `updateMessage` are channel-aware); two TanStack hooks (`useIdeationMessages`, `useSendIdeationMessage`); `<IdeationDrawer />` (slides from right, 40vw/max-560px desktop, full-screen mobile, empty-state with 4 clickable suggestions, inline amber error block, `aria-modal="true"` + `role="alert"`); `<IdeateButton />` with URL hash sync (`#ideate`); mounted on the proposal page header.
- Plus the cross-cutting fix commit `91bb135` (worker error path now also publishes `new_message` so the drawer renders the error in real time; `send_ideation_message` no longer broadcasts `typing` since `isTyping` is a single shared flag and was leaking into the main chat; Alembic migration now uses `op.get_context().autocommit_block()` + `postgresql_concurrently=True` for safe prod deploy on the hot `chat_messages` table; WS hook gains `pipeline_error` handler + the TS type union).

**Outstanding immediate work for the next session:**

- **Task 17 docker smoke test ✅** passed — drove a real two-turn Bedrock conversation end-to-end in the browser, confirmed channel isolation in DB + API, confirmed the read-only invariant on `pipeline_state`, and confirmed the no-typing-leak fix from `91bb135`. Details under "What's queued / Option A" below. The forced-failure path was NOT exercised live (worker AWS mount is read-only) — unit coverage is comprehensive.
- **Register-flow React #31 crash ✅ FIXED** in commit `b363d6f` — `formatApiError(err, fallback)` helper in `frontend/src/api/client.ts` now safely renders Pydantic 422 array responses as a joined `msg` string. The previously-reported "frontend sends `name` instead of `full_name`" was a misattribution (auth-store sends `full_name` correctly; the smoke-test 422 came from the email validator rejecting `.local`). See Option C below for details.
- **Loose ends on main's working tree ✅ DONE**: brief_analyzer Haiku switch committed (`0ef10dd`); duplicate `fly-deploy.yml` deleted (the existing `deploy.yml` placeholder remains, with auto-deploy commented out until Fly secrets are set). Working tree fully clean. See Option B for details.
- **Production:** `fly.toml` still needs AWS secrets set via `fly secrets set` before a real deploy can complete (see "Deployment" below). Unchanged from the previous session.

---

## Where to look for what

| Thing | Path |
|---|---|
| Specs | `docs/superpowers/specs/` |
| Plans | `docs/superpowers/plans/` |
| **This file** | `docs/superpowers/HANDOFF.md` |
| Project memory (loaded each session) | `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/` |
| Global CLAUDE.md | `~/.claude/CLAUDE.md` |
| Backend tests | `backend/tests/{unit,integration}/` |
| Frontend tests | `frontend/src/**/__tests__/` |
| Docker stack | `docker-compose.yml` + `Dockerfile` + `.env.docker` (gitignored) |
| Fly deploy config | `fly.toml` (secrets set out-of-band via `fly secrets set`) |

---

## Repo state at handoff

```text
origin/main = 91bb135 = local main
Working tree: modified
  M backend/app/services/ai/brief_analyzer.py     (Haiku-tier switch — uncommitted)
  ?? .github/workflows/fly-deploy.yml             (untracked, 18 lines)
```

Recent history (newest first — top 16 are this session's merge):

```
91bb135 fix: ideation real-time error delivery, typing isolation, migration safety
5b82c89 feat(ui): mount IdeateButton and IdeationDrawer on the proposal page
58b8638 feat(ui): IdeateButton with URL hash sync
e3b2c16 feat(ui): IdeationDrawer with empty state, message list, send, and error rendering
fdcb491 feat(api): useIdeationMessages and useSendIdeationMessage hooks
aba6670 feat(store): route incoming chat messages by channel into separate slices
3489500 feat(types): ChatMessage carries the channel field
34795d8 feat: GET /chat/{id}/ideation/messages and POST /chat/{id}/ideation/send
f32c087 feat: ChatViewModel.get_ideation_messages and send_ideation_message
4a488d5 feat: run_ideation worker task with isolated failure handling
758ef06 test: IdeationService propagates Bedrock errors instead of swallowing
e235451 feat: IdeationService.run_ideation — Sonnet 4.6 + cache_control + ideation-channel commit
47e9542 feat: _build_ideation_system_prompt — read-only proposal context for the side-channel
403643a feat: ChatMessageResponse exposes the channel field
ff8cb78 feat: ChatMessageRepository.list_by_proposal filters by channel
62ed9d9 feat: add chat_messages.channel column for ideation side-channel
97472da docs: session handoff for resume after /clear     (← session boundary)
51af281 feat(ui): route new research / benchmarks message types in MessageBubble
…
```

### Test suites (verified green at handoff)

```bash
cd backend && .venv/bin/python -m pytest -q
# → 244 passed, 0 skipped  (was 224 pre-ideation; +20 new tests)

cd frontend && pnpm test --run
# → 115 passed across 24 files  (was 101 pre-ideation; +14)

cd frontend && pnpm build
# → clean

.venv/bin/python -c "from app.main import app; print(len(app.routes))"
# → 64   (was 62; +2 ideation routes)
```

---

## What got done today (in execution order)

The whole session was a single skill invocation: `superpowers:subagent-driven-development` against the previously-written 17-task plan. Worktree created via `EnterWorktree`, all 16 code tasks executed in there, then fast-forward merged to main and `ExitWorktree(action: remove)` for cleanup.

### Per-task lifecycle (each task)

1. Mark in_progress in TaskCreate.
2. Dispatch implementer subagent (Haiku for mechanical, Sonnet for integration). Full task text + scene-setting inlined into the prompt; subagent does NOT read the plan file.
3. Dispatch spec-compliance reviewer (Haiku) with the same task text. Verifies by reading code, not by trusting the implementer.
4. If spec issues: re-dispatch implementer with the specific gaps, then re-review.
5. Dispatch code-quality reviewer (Sonnet for non-trivial changes, Haiku for ≤2-file additions). 5-axis review + the focus areas the controller flagged in the prompt.
6. If quality issues: re-dispatch implementer with the specific fixes (`git commit --amend --no-edit` for atomic per-task commits).
7. Mark completed.

### Cross-cutting final review

After all 16 tasks landed, dispatched a final cross-cutting reviewer (Sonnet) over the full branch diff. It caught two Critical bugs the per-task reviewers missed because they were only visible at the full-stack level:

1. **Error path didn't publish `new_message`** — the worker wrote a `system/error` row and committed it, but only published `pipeline_error`. The frontend had no `pipeline_error` handler for the ideation channel, so an open drawer never saw the error in real time. **Fix:** the worker now publishes BOTH events (the `new_message` for the row, then the `pipeline_error` for observability).
2. **`isTyping` cross-contamination** — `send_ideation_message` broadcast `{type: "typing", typing: true}`, but `isTyping` is a single shared scalar in the frontend store. Sending an ideation message lit up "AI is thinking..." in the MAIN chat panel. **Fix:** removed the typing broadcast entirely from ideation. The drawer's `useSendIdeationMessage` mutation's `isPending` state disables the Send button, providing optimistic feedback. A channel-aware typing indicator is a follow-up.

Plus two Important fixes:
- `op.get_context().autocommit_block()` + `postgresql_concurrently=True` on the `chat_messages` index (prod safety on a hot table).
- WS hook test gained an end-to-end channel-routing test.

And one Suggestion: `pipeline_error` added to the TS `WSMessage.type` union + a no-op `console.warn` handler in `use-websocket.ts` for observability.

All five rolled into commit `91bb135`.

### Operational recovery worth remembering

Task 12 (frontend API hooks) — the implementer subagent ran `cd /Users/karthikramesh/Developer/nuprop/frontend` (the MAIN checkout's frontend, not the worktree's), then wrote files and committed there. The commit `61f619b` landed on `main` instead of on the worktree branch. Caught by the implementer's report: test count went from 104 to 103 instead of 106 (running against main's frontend, which lacked Tasks 10/11). Recovery:

1. `git cherry-pick 61f619b` from inside the worktree → applied cleanly (the commit only touched 2 files that the worktree branch hadn't yet modified).
2. `git stash push -- backend/app/services/ai/brief_analyzer.py` on main → `git reset --hard 97472da` → `git stash pop`. The brief_analyzer mod survived, the bad commit disappeared from main.
3. Confirmed `git status` on main: clean except the original 2 loose ends.

After this incident, every subsequent frontend-task subagent prompt got a defensive preamble: "ALWAYS prefix `cd frontend && ...` with the FULL worktree path: `cd /Users/karthikramesh/Developer/nuprop/.claude/worktrees/ideation-side-channel/frontend && ...`. Before commit, ALWAYS run `git branch --show-current` to confirm." No subsequent contamination.

---

## What's queued for the next session

### Option A — Task 17 live docker smoke test ✅ COMPLETED 2026-05-16

Ran via `docker compose up --build -d` + Playwright. Stack came up clean, migration `02_ideation_channel` applied, worker registered all 7 functions including `run_ideation`. Drove a real Bedrock round-trip end-to-end:

- Drawer renders correctly (40vw right slide, empty state with 4 suggestions, `role="dialog"` + `aria-modal="true"`).
- URL hash sync works both ways (open → `#ideate`, refresh-with-`#ideate` reopens, close clears).
- Suggestion click populates the input without auto-sending.
- Two-turn conversation against Sonnet 4.6 — first turn 6.55s, second 7.30s. Both replies substantive and grounded in the empty-brief context (proves `_build_ideation_system_prompt` reaches Bedrock correctly).
- **Critical-fix verification:** no typing leak into the main chat panel during ideation processing (`mainHasTyping: false` while the drawer was awaiting).
- Channel isolation at both DB level (all 4 rows `channel="ideation"`, main has 0) and API level (`GET /chat/{id}/messages` → `[]`; `GET /chat/{id}/ideation/messages` → 4).
- Read-only invariant: `pipeline_state.current_phase` still `"brief"`, `proposal.brief` still `{}` after both turns.
- Per-turn idempotency: worker logs show two distinct `run_ideation:<user_msg_id>` job IDs.

**Skipped:** forced-failure path. The worker container's `/root/.aws` mount is read-only, so triggering a Bedrock auth failure would require a worker restart with a bad `AWS_PROFILE` override. Unit coverage for that path is comprehensive (`test_run_ideation_propagates_bedrock_errors`, `test_run_ideation_task_records_error_message_on_failure`, plus the `new_message`-publish-on-error assertion added in `91bb135`). Worth a one-off live test eventually but low-priority.

**Two pre-existing frontend bugs surfaced during the smoke test** (unrelated to ideation — see Option C below).

### Option B — Loose-ends cleanup ✅ DONE

1. **`backend/app/services/ai/brief_analyzer.py`** — committed as `0ef10dd feat: switch brief_analyzer to Haiku 4.5 for chat felt-latency`. Brief intake (both `analyze` and `analyze_stream`) now uses Haiku 4.5 for 3-5× faster TTFT on the conversational loop. Full backend suite passes unchanged.
2. **`.github/workflows/fly-deploy.yml`** — deleted (untracked → removed from disk; no commit needed). It was the auto-on-push template generated by `fly launch`, duplicating the existing `deploy.yml` placeholder which has `push:` commented out with `# Disabled until Fly.io app is created and FLY_API_TOKEN secret is set`. Decision was to keep the placeholder and flip its comment when production secrets are set (see Option E).

### Option C — Frontend register-flow bug ✅ FIXED (commit `b363d6f`)

Originally flagged as two bugs after the smoke test. On follow-up inspection only ONE was real:

- **~~`/register` sends `name` instead of `full_name`~~** — NOT A BUG. `auth-store.ts:29` already sends `full_name: fullName` correctly. My smoke-test report conflated my own manual `curl` (which DID post `name`) with what the frontend does. The 422 from the live UI was actually from the email validator rejecting `.local`.
- **React error #31 on rendering 422 responses** — REAL. Fixed: new helper `formatApiError(err, fallback)` in `frontend/src/api/client.ts` returns a string from any axios-error shape (Pydantic 422 array gets `msg` fields joined with `; `; HTTPException string detail passes through; unknown shapes fall back). Applied at the two crash sites: `pages/auth/register.tsx:22` and `pages/proposals/new.tsx:25`. 5 new vitest cases lock the contract (`client.test.ts`). 120 frontend tests pass.

Bonus context still valid: `@test.local` is rejected by the email validator (`The part after the @-sign is a special-use or reserved name`). Use `.com` / `.test` / `.example` for test accounts. Not a bug, just a footgun.

### Option D — Reviewer follow-ups ✅ ALL THREE COMPLETED (2026-05-16)

All three landed in the following commits, each with its own dedicated review-driven scope:

1. **`6a51d69 test: consolidate _make_proposal helpers into shared fixtures`** — added `make_proposal_db` (returns `(agency, client, proposal)`) and `make_proposal_api` (returns proposal dict) factories in `conftest.py`. Removed 10 local `_make_proposal` helpers + the `_client_proposal_via_api` helper from `test_ideation_api.py`. 244 tests still pass.
2. **`070b4e1 perf(ui): O(n) ideation hydration via mergeIdeationMessages store action`** — new `mergeIdeationMessages(msgs)` store action does a Set-based dedup in a single pass. `IdeationDrawer`'s hydration `useEffect` now calls it instead of looping `addMessage`. 4 new vitest cases. Frontend goes from 120 → 124 passing.
3. **`dbd081c feat(ui): channel-aware typing indicator for the ideation drawer`** — backend reinstates the typing broadcast in `send_ideation_message` with `channel: "ideation"` on the payload. Frontend store gains `isIdeationTyping: boolean` + `setIdeationTyping`. WS hook routes `typing` events by `data.channel` (defaulting to main when omitted, back-compat). `new_message` on the ideation channel clears `isIdeationTyping`, not `isTyping`. Drawer renders `<TypingIndicator />` inside the message area when `isIdeationTyping` is true. 7 new vitest cases lock the channel routing + no-leak invariant. Frontend goes from 124 → 131 passing.

After these landed: backend 244, frontend 131, tsc clean, vite build clean. Pushed in one batch: `0ef10dd..dbd081c main -> main`.

### Option D-LEGACY (kept for context) — Follow-ups flagged by reviewers during the ideation build

Deferred to keep the branch tightly scoped to the ideation feature:

- **`_make_proposal` test-helper duplication** — now lives in 10 integration test files. Promote to a shared `pytest_asyncio.fixture` in `conftest.py` that accepts optional `brief` / `pipeline_state` kwargs.
- **Channel-aware typing indicator** — V1 just removed the leaky broadcast. Add an `isIdeationTyping: boolean` slice + render `<TypingIndicator />` inside `IdeationDrawer` + route `typing` events by channel.
- **Drawer hydration O(n²)** — `useEffect` calls `addMessage` per message on every TanStack refetch; `addMessage` dedupes via `.some()`. For 200-message threads that's 40k comparisons per window-focus. Add a store action that does a single O(n) merge.
- **Documentation:** the in-repo HANDOFF (this file) is current, but the spec's WS event catalogue should also list the `pipeline_error.phase` values now in use and confirm `message_updated` is channel-aware.

### Option E — Production deploy ✅ LIVE (2026-05-16)

NUPROP is live at **https://nuprop.fly.dev** — health endpoint returns 200, login page renders.

**Final stack:**
- App + worker on Fly Mumbai (`bom`), image `nuprop:deployment-01KRRF07PX0M8TDXQEW6NDHPGS`. App: `shared-cpu-2x` 1GB, attached to `nuprop_data` volume. Worker: 1 active + 1 standby.
- Postgres: **Neon free tier** in `us-east-1` (note: cross-region from `bom` → ~200ms per query; user opted to ship now and migrate region later via Neon's branching). DATABASE_URL uses `?ssl=require` (SQLAlchemy asyncpg dialect form), NOT the libpq `?sslmode=require` form.
- Redis: **Upstash free tier** in regional plan. **REDIS_URL must use `rediss://` (TLS) — plain `redis://` causes Upstash to drop the connection server-side**. Worker and app both consume the same URL via redis-py; both rely on the `rediss://` scheme to auto-enable SSL.
- LLM: AWS Bedrock `ap-northeast-1` via the `karthik` personal IAM user's keys (staged from local `~/.aws`).
- All 6 secrets `Deployed` on Fly.

**Deploy gotchas discovered today:**
- **Upstash requires TLS.** First deploy used `redis://`; app crashed on every connect with `ConnectionError: Connection closed by server`. Worker's ARQ pool also failed silently. Fix: `rediss://` (two s's).
- **Crash-looping machine holds its lease.** While the app was in a startup crash loop, `fly secrets set` couldn't acquire the machine's lease to apply new secrets. Had to kill the in-flight `fly deploy` first, then re-stage and re-deploy.
- **Rolling updates can leave one machine on the old image.** Second deploy successfully rolled the worker(s) but failed to acquire the app machine's lease (still contested by the dead in-flight deploy). Third deploy with all leases free finally rolled all three machines to the new image.
- **`fly secrets deploy` refuses if no machine is in a "deployed" state.** After cancelling a failed deploy, only `fly deploy` (not the cheaper `fly secrets deploy`) can apply new secrets.

**Resume / iterate flow:**

```bash
# Every push from now on:
git push origin main         # nothing automatic yet (Actions workflow disabled)
fly deploy -a nuprop --remote-only

# To enable auto-deploy on push:
fly tokens create deploy     # outputs a token
# Add it to GitHub repo secrets as FLY_API_TOKEN
# Edit .github/workflows/deploy.yml — uncomment the `push:` block

# To watch logs:
fly logs -a nuprop

# To restart without redeploy (e.g., to pick up new staged secrets):
fly secrets deploy -a nuprop
```

---

### Option E-LEGACY — Production deploy 🟡 PARTIALLY STAGED (paused 2026-05-16 — superseded by completion above)

Started the deploy run. Got blocked on infra-provisioning decisions; stopped after staging the secrets I could set without third-party signups.

**What's been done on Fly:**

- App `nuprop` exists in `bom` (Mumbai) with the right `fly.toml` (release_command `alembic upgrade head`, app+worker processes, /data volume mounted, force HTTPS, health check on `/api/v1/health`).
- 4 secrets **staged** (not deployed yet — they'll go live on first `fly deploy`):
  ```
  JWT_SECRET_KEY        (freshly generated with `openssl rand -hex 32`)
  AWS_ACCESS_KEY_ID     (pulled from local ~/.aws — user `karthik`, account 809644065208)
  AWS_SECRET_ACCESS_KEY
  AWS_REGION            (ap-northeast-1)
  ```
  Verify with `fly secrets list -a nuprop`.

**What's still needed before `fly deploy`:**

- `DATABASE_URL` — user picked **Neon** (free tier, ~3GB, faster sign-up than Supabase). User signs up at https://neon.tech, creates a project, copies the asyncpg URL (`postgresql+asyncpg://<user>:<pw>@<host>/<db>?sslmode=require`). Then `fly secrets set DATABASE_URL=...`. Neon's connection-pooler URL (port 6543) does NOT work with asyncpg's prepared statements — use the **direct** URL.
- `REDIS_URL` — user paused on this. Fly's Upstash starts at $10/mo (Fixed 250MB) — no free tier on the Fly-managed integration. The alternative is upstash.com direct (free tier: 256MB / 10K commands/day, plenty for ARQ + WS pub/sub). Three paths from here:
  1. `fly redis create -n nuprop-redis --plan "Fixed 250MB" --region bom` ($10/mo, integrated)
  2. Sign up at upstash.com (free, slightly outside Fly's network)
  3. Defer Redis: deploy with no `REDIS_URL` — backend boots, but ARQ workers + WS pub/sub silently fail until it's set. Brief intake + ideation would not function.

**Resume flow (when user is ready):**

```bash
# 1. Set the two remaining secrets
fly secrets set -a nuprop \
  DATABASE_URL="postgresql+asyncpg://...@...neon.tech/nuprop?sslmode=require" \
  REDIS_URL="redis://default:...@...upstash.io:6379"
# (the 4 staged secrets auto-deploy alongside these)

# 2. Deploy
fly deploy -a nuprop --remote-only

# 3. Watch the release_command (alembic) run cleanly + machines come up
fly logs -a nuprop

# 4. Verify
curl -s -o /dev/null -w "%{http_code}\n" https://nuprop.fly.dev/api/v1/health
# → 200
```

**Then flip the GitHub Actions auto-deploy on:** edit `.github/workflows/deploy.yml`, uncomment the `push: branches: [main]` block, add `FLY_API_TOKEN` to the repo's GitHub Actions secrets (`fly tokens create deploy` outputs one). Every push to main then auto-redeploys.

Same as the previous handoff. `fly.toml` is configured. Secrets not set:

```bash
fly secrets set -a nuprop \
  DATABASE_URL="postgresql+asyncpg://postgres:<pw>@<host>.supabase.co:5432/postgres" \
  REDIS_URL="redis://default:<token>@<host>.upstash.io:6379" \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id)" \
  AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key)" \
  AWS_REGION="ap-northeast-1"
```

The ideation migration uses `postgresql_concurrently=True` so it won't lock the hot `chat_messages` table on first prod deploy. Safe.

---

## Architecture deltas worth remembering

### `IdeationService` is read-only by construction

`backend/app/services/ideation_service.py` does NOT call `ProposalRepository.update` anywhere. The class can read `proposal` (via `get_by_id`) but has no write surface for `proposal.*` fields. The only writes are to `chat_messages` with `channel="ideation"`. There are two tests that prove this:
- `test_run_ideation_does_not_mutate_proposal_fields` — fingerprints `brief`/`research`/`cost_model`/`covering_letter`/`pipeline_state` before/after and asserts unchanged.
- `test_run_ideation_task_does_not_touch_pipeline_state` — same for the worker wrapper.

### Worker failure isolation

`_run_ideation_phase` in `backend/app/workers/pipeline.py` has its own `try/except` and does NOT call `_set_job_status`. On failure it writes a single `chat_messages` row (role=`system`, `extra_data.kind="error"`, `channel="ideation"`) **and** publishes both a `new_message` event for that row and a `pipeline_error` event. The user-facing `content` is sanitized to a generic `"Couldn't reach Bedrock. Send another message to try again."`; full exception detail lives in `extra_data.error` for engineering.

### Commit-before-broadcast (locked in with a spy test)

`IdeationService.run_ideation` follows the same pattern as the main pipeline: `await self.session.commit()` BEFORE `await self._emit_message(...)`. Test `test_run_ideation_commits_before_broadcasting` installs a spy on `publish` that opens a fresh session inside the callback and asserts the row is already visible at that exact moment. If anyone ever reorders the two lines, this test fails immediately.

### Prompt caching for the ideation system block

The proposal-context system prompt (built by `_build_ideation_system_prompt`) is passed as a list-form block with `cache_control: {"type": "ephemeral"}`. For a brand-new proposal it's ~250-300 tokens (below the 1024-token cache minimum — Bedrock silently bypasses), but for a developed proposal (brief + research + cost model + narrative) it can reach 6-8k tokens, which caches well for multi-turn ideation: turn 1 ~3-5s, turn 2+ ~85% input-token cost reduction and ~1s faster TTFT.

### Frontend store: two slices, both channel-aware

`frontend/src/stores/chat-store.ts` has parallel `messages` and `ideationMessages` slices. **Both** `addMessage` and `updateMessage` route by `msg.channel === 'ideation'`. The latter was fixed during Task 13's review — originally `updateMessage` only touched `state.messages`, which would have silently dropped any future `message_updated` events on the ideation channel. (Currently the ideation worker only emits `new_message`, so `updateMessage` is dormant for ideation, but the routing is in place for when streaming lands.)

---

## Gotchas that are easy to forget

### Working directory drift (now with extra teeth)

Bash commands persist `cwd` between calls in the harness. The original gotcha from the previous handoff still applies — backend pytest needs `cd backend &&` first, frontend pnpm needs `cd frontend &&`. **This session added a new failure mode:** when working in a worktree, an implementer subagent doing `cd /Users/karthikramesh/Developer/nuprop/frontend` (the main checkout's frontend, not the worktree's) silently contaminates main. Defensive pattern that worked for the remaining tasks:

> "ALWAYS prefix bash commands with the absolute worktree path. Before commit, run `git branch --show-current` and confirm you're on the worktree branch."

Build that into every implementer prompt for the next subagent-driven session.

### Postgres uses VARCHAR(36), not native UUID
Unchanged. Pass strings, not UUID objects, to anything that compares ID columns. `BaseRepository._coerce_id` always `str()`s; `ChatMessage.proposal_id == str(proposal_id)` is the pattern.

### ARQ behavior
Unchanged. Bare `raise` does NOT auto-retry. The main pipeline's `_run_phase` and ideation's `_run_ideation_phase` both treat every exception as terminal. For ideation, the user re-prompts (each prompt is a fresh job_id keyed on `user_msg.id`). Main-pipeline gates use the bare `{proposal_id}:{phase}` job_id form for one-shot click-through; ideation always uses the per-turn form.

### Bedrock model IDs (verified)
```
Heavy    : global.anthropic.claude-opus-4-7
Balanced : global.anthropic.claude-sonnet-4-6        (NOT -v1)
Fast     : global.anthropic.claude-haiku-4-5-20251001-v1:0
```
Ideation uses `Tier.BALANCED` (Sonnet 4.6). Verified via `aws bedrock list-inference-profiles --region ap-northeast-1`.

### Opus 4.7 constraints
Unchanged. No `temperature`/`top_p`/`top_k`. `thinking={"type": "adaptive"}` only. `AIService._build_kwargs` strips these when `tier == Tier.HEAVY`. Ideation doesn't hit this path today (it uses BALANCED), but if you ever flip it to HEAVY, also strip `temperature=0.7` from the `messages_create` call — there's an inline note in `ideation_service.py` flagging this.

### `_no_network` test guard
Unchanged. `backend/tests/conftest.py:_no_network` patches `AnthropicClient.*` and `is_configured` so accidental real calls fail loudly. The ideation tests bypass this guard cleanly by monkeypatching `get_ai_service` directly to return a `_StubAI` — no conflict with the autouse guard.

### WebSocket event types catalogue

Updated this session:

- `new_message` — fresh chat message. Carries `channel` field. Frontend routes by `channel`.
- `message_updated` — existing message's full state changed (e.g., activity log got more events). Frontend's `updateMessage` IS channel-aware (this session's fix) but the ideation worker only emits `new_message`, so the routing is dormant for ideation today.
- `typing` — typing-indicator toggle. **`isTyping` is a single shared scalar.** Ideation does NOT emit this (would contaminate main chat). A channel-aware version is a follow-up.
- `phase_change` — main pipeline's `current_phase` changed. Ideation does NOT emit this.
- `progress` — per-phase progress. Ideation does NOT emit this.
- `pipeline_error` — terminal phase failure. NEW shape: `{type, phase, error}`. Main pipeline emits `phase: "research"`, `"build_cost_model"`, etc. Ideation emits `phase: "ideation"` (not `"run_ideation"` — the function-name form was rejected in review for being internal). Frontend hook has a no-op `console.warn` handler; the user-facing error message arrives as a separate `new_message` with `role=system`, `extra_data.kind="error"`.

### Channel-by-message routing on the frontend

`chat-store.ts` has TWO slices: `messages` (channel "main") and `ideationMessages` (channel "ideation"). Both `addMessage` and `updateMessage` route by `msg.channel`. `setMessages` is main-only by design (used by initial hydration of the main pipeline). The drawer hydrates from `useIdeationMessages` by iterating the response and calling `addMessage` per row (dedupes by id) — O(n²) per refetch, fine for short threads, flagged as follow-up for long ones.

---

## Deployment status

Unchanged structurally from the previous session. Ideation's Alembic migration uses `op.get_context().autocommit_block()` + `postgresql_concurrently=True`, so `CREATE INDEX` on `chat_messages` won't lock the table during first prod deploy. Otherwise: `fly.toml` ready, secrets not set, no CI workflow live yet (the untracked `fly-deploy.yml` is a candidate to commit if it's the right shape — needs inspection).

---

## How to resume

1. Read this file end-to-end (~3 min).
2. `git log --oneline -5`, `git status` — confirm the latest `docs:` commit is HEAD and the two loose ends still pending.
3. `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/session_handoff_2026_05_16.md` has the same pointer + a quick-verification block.
4. Every queued item from this session is ✅ done — A (smoke test), B (loose ends), C (register-flow), D (reviewer follow-ups, ×3), E (production deploy). NUPROP is live at **https://nuprop.fly.dev**. Next session's open menu is the older PRD backlog (M16-M20: client context + connectors), or housekeeping (`.local` TLD note in CLAUDE.md, GitHub Actions auto-deploy wire-up, dedicated AWS IAM user for Bedrock).
