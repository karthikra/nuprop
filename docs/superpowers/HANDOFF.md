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

- **Task 17 — live docker smoke test.** Not blocking — feature is merged to main and pushed. Manual UI verification: `docker compose up --build -d`, register, create proposal, click the Ideate button in the header, drive a thread. Plan's Task 17 has the explicit checklist.
- **Loose ends on main's working tree** (untouched throughout this session, both from a prior session): uncommitted `backend/app/services/ai/brief_analyzer.py` (Haiku-tier switch — 10-line change) and untracked `.github/workflows/fly-deploy.yml` (18 lines, looks like an early CI deploy attempt). Decide commit / revert / amend.
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

### Option A — Task 17 live docker smoke test

Plan's checklist (`docs/superpowers/plans/2026-05-15-ideation-side-channel.md`, Task 17). In short:

```bash
cd /Users/karthikramesh/Developer/nuprop
docker compose up --build -d
# wait: curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/health  → 200
# browser → register → create proposal → click "💡 Ideate" in header
```

Things to verify during the smoke test:
- The drawer slides in from the right (40vw, capped at 560px on desktop).
- Empty state shows 4 clickable suggestions; clicking one inserts text into the input (does NOT auto-send).
- After sending: user bubble appears immediately in the drawer; Send button disables while pending; ~5-10s later the assistant reply arrives via WS.
- **Critically:** the MAIN chat panel shows NO "AI is thinking..." while the ideation drawer is processing (the regression Task 91bb135 fixed).
- If you force a failure (kill Bedrock creds), an amber error block appears INLINE in the drawer thread within seconds — not on refresh (this is the real-time delivery Task 91bb135 fixed).
- Refresh with `#ideate` in the URL — the drawer auto-reopens.
- `pipeline_state.current_phase` on the proposal is unchanged after ideation turns (the read-only invariant — verify in psql).

### Option B — Cleanup pass on the loose ends

1. `backend/app/services/ai/brief_analyzer.py` — uncommitted Haiku-tier switch (10 lines, looks intentional and reasonable). Either commit as `feat: switch brief_analyzer to Haiku 4.5 for chat felt-latency` or revert if you decide Sonnet is the right tier for brief intake.
2. `.github/workflows/fly-deploy.yml` — untracked, 18 lines. Inspect; either commit as a deploy automation or delete.

### Option C — Follow-ups flagged by reviewers during this session

Deferred to keep the branch tightly scoped to the ideation feature:

- **`_make_proposal` test-helper duplication** — now lives in 10 integration test files. Promote to a shared `pytest_asyncio.fixture` in `conftest.py` that accepts optional `brief` / `pipeline_state` kwargs.
- **Channel-aware typing indicator** — V1 just removed the leaky broadcast. Add an `isIdeationTyping: boolean` slice + render `<TypingIndicator />` inside `IdeationDrawer` + route `typing` events by channel.
- **Drawer hydration O(n²)** — `useEffect` calls `addMessage` per message on every TanStack refetch; `addMessage` dedupes via `.some()`. For 200-message threads that's 40k comparisons per window-focus. Add a store action that does a single O(n) merge.
- **Documentation:** the in-repo HANDOFF (this file) is current, but the spec's WS event catalogue should also list the `pipeline_error.phase` values now in use and confirm `message_updated` is channel-aware.

### Option D — Production deploy

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
2. `git log --oneline -5`, `git status` — confirm `91bb135` is HEAD and the two loose ends still pending.
3. `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/session_handoff_2026_05_16.md` has the same pointer + a quick-verification block.
4. Ask the user which queued item to pick — A (smoke test), B (loose-ends cleanup), C (review follow-ups), D (production deploy). Default if they want momentum: **A**, since it's the last unverified gap on a freshly-merged feature.
