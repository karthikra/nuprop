# NUPROP Session Handoff

**Last updated:** 2026-05-15 (end of working session)
**Latest commit on `main`:** `51af281` (pushed to `origin/main`)
**Working tree:** clean. Branch: `main`. No worktrees.

> Quick orientation: this doc gets you from a `/clear` to "ready to keep working" in under two minutes. The current state, the two queued workstreams, the gotchas, and the exact next decisions are all below.

---

## TL;DR

NUPROP is a multi-tenant AI proposal copilot. Today (a single working session) shipped two major refactors and one feature build, all on `main`:

1. ✅ **Background-worker pipeline** — moved the proposal pipeline (research → cost model → narrative → outputs) off the HTTP request thread onto an ARQ worker so each phase commits before broadcasting. Fixed the read-your-writes bug.
2. ✅ **Bedrock migration** — every Claude call now routes through `AsyncAnthropicBedrock` per the project's CLAUDE.md policy. Sonnet 4.6 default, Opus 4.7 for research, Haiku 4.5 for fast chat/plans.
3. ✅ **Research transparency** — pre-flight plan + live activity log + annotated findings (with hover-citation superscripts) for `run_research` and `run_benchmarks`.

**Plus a fourth feature was fully designed but NOT executed:** the **Ideation side-channel** — spec + 17-task plan written and approved, queued for execution.

**Outstanding immediate work for the next session:**

- **Decide:** execute the queued ideation plan, or do a live smoke test of the research-transparency build first.
- **Stretch:** clean up minor lint items (unused imports, inline-import placements flagged by code review) and the stale `ANTHROPIC_API_KEY=…` line in `.env.docker`.
- **Production:** `fly.toml` still needs AWS secrets set via `fly secrets set` before a real deploy can complete (see "Deployment" below).

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
origin/main = 51af281 = local main = clean working tree
```

Recent history (newest first, all today):

```
51af281 feat(ui): route new research / benchmarks message types in MessageBubble
5f8a0b7 feat(ui): ResearchFindingsCard — annotated findings with hover citation superscripts
e2f8e3c feat(ui): CitationPopover — dumb popover with title, domain, snippet, source link
7475f7f feat(ui): ResearchActivityLog — live timeline with collapse-on-complete
0e6cc59 feat(ui): ResearchPlanCard — renders pre-flight plan for research and benchmarks
82ec667 feat(store): updateMessage action + WS message_updated routing
86436f6 test: migrate / retire tests that monkeypatched old ResearchAgent/BenchmarkAgent paths
13f38d7 feat: run_benchmarks emits separate plan/activity/findings (Sonnet 4.6 streaming)
27c77e0 fix: run_research formats RESEARCH_SYSTEM template before sending to Bedrock
5b8cbb9 feat: run_research emits plan + activity log + annotated findings (Opus 4.7 streaming)
d7de977 fix: process_stream — compute span offsets from cited_text, handle results at content_block_stop
3e374b6 feat: process_stream — SDK stream → ActivityEvents + body + citation graph
7642613 feat: ActivityFlusher — batched-flush primitive for live activity logs
4a50588 feat: Haiku-based research_planner — research + benchmarks plan generation
1ec3b95 feat(events): publish_message_updated helper for live message updates
1975019 docs: implementation plan for research transparency feature
10b1959 docs: spec for research transparency — plan, live activity, annotated findings
ff75d26 fix: restore web-search tool-use after Bedrock migration
8f694e7 docs: implementation plan for ideation side-channel
dc8a55f docs: spec for ideation side-channel feature
98ca061 feat: route Claude inference through AWS Bedrock (CLAUDE.md compliance)
…
```

### Test suites (verified green at handoff)

```bash
cd backend && .venv/bin/python -m pytest -q
# → 224 passed, 0 skipped

cd frontend && pnpm test --run
# → 101 passed across 21 files

cd frontend && pnpm build
# → clean
```

---

## What got done today, in order

### 1. Background-worker pipeline (20 tasks, all executed inline)

Goal: move the multi-phase proposal pipeline off the HTTP request thread onto ARQ background jobs so each phase commits its DB writes before it broadcasts — fixing the read-your-writes bug. Spec at `docs/superpowers/specs/2026-05-15-background-worker-pipeline-design.md`, plan at `docs/superpowers/plans/2026-05-15-background-worker-pipeline.md`.

Shipped:
- ARQ worker process (`app/workers/pipeline.py`) running six phase functions.
- New `PipelineService` (`app/services/pipeline_service.py`) — each phase commits before broadcasting, ~570 lines extracted from `ChatViewModel`.
- Redis pub/sub bridge (`app/infrastructure/queue/events.py`) — worker emits go to `nuprop:ws` channel; API process's `ws_event_subscriber` (started in lifespan) relays to local `ws_manager`.
- `ChatViewModel` slimmed 832 → 263 lines; now just validates, persists user msg, enqueues the first phase, returns immediately.
- `POST /chat/{id}/retry` endpoint for failed phases.
- Docker-compose + fly.toml updated for the worker process.

Live smoke test exposed several pre-existing bugs (see "Smoke test discoveries" below). All fixed before move-on.

### 2. Bedrock migration (one big commit `98ca061`)

The codebase was hitting `api.anthropic.com` directly with `ANTHROPIC_API_KEY`, violating CLAUDE.md's "always route through AWS Bedrock" rule. Migrated every AI call:

- New `app/services/llm.py` — canonical `AIService` per MVVM. Wraps `AsyncAnthropicBedrock`. Three tiers (`FAST`/`BALANCED`/`HEAVY`), Opus 4.7-aware kwargs builder (strips `temperature`/`top_p`/`top_k`).
- Rewrote `app/infrastructure/external/anthropic_client.py` as a facade over `AIService` (preserves existing agents' surface).
- Dropped `ANTHROPIC_API_KEY` from config; added `AWS_REGION` (default `ap-northeast-1`) and optional `AWS_PROFILE`.
- Model IDs updated to verified Bedrock global inference profile IDs:
  - Default (Sonnet 4.6): `global.anthropic.claude-sonnet-4-6`
  - Opus 4.7: `global.anthropic.claude-opus-4-7`
  - Haiku 4.5: `global.anthropic.claude-haiku-4-5-20251001-v1:0`
- `docker-compose.yml`: dropped `ANTHROPIC_API_KEY` env, added `AWS_REGION` + read-only `~/.aws` mount into both `app` and `worker`.

Three documentation discrepancies surfaced (and were fixed in source-of-truth files):
- **`AsyncAnthropicBedrockMantle` doesn't exist** — both `~/.claude/CLAUDE.md` and the `anthropic-pipeline` skill referenced this nonexistent class. Real SDK exports `AsyncAnthropicBedrock` (no "Mantle"). Both docs corrected.
- **Sonnet 4.6 model ID had wrong `-v1` suffix** in the skill — actual is `global.anthropic.claude-sonnet-4-6`.
- **Haiku 4.5 model ID** in the skill was the on-demand foundation-model ID, not the global inference profile (`global.anthropic.claude-haiku-4-5-20251001-v1:0`).

### 3. Two bug fixes after live smoke testing (`ff75d26`, `15dfeef`)

**`ff75d26` — Web-search tool-use after Bedrock migration:** `ResearchAgent` and `BenchmarkAgent` reached into `self._client._client.messages.create(...)` for native web search. The Bedrock migration renamed the facade's internal client `_client` → `_ai`, so both agents crashed with `AttributeError: 'AnthropicClient' object has no attribute '_client'`. Added a public `AnthropicClient.messages_create(**kwargs)` method that proxies to `AIService.messages_create`, and updated both agents to use the public surface. Plus a `test_anthropic_facade.py` that locks in the facade's public methods so any future rename fails fast.

**`15dfeef` — Per-turn unique job IDs for analyze_brief:** ARQ uses `_job_id` as an idempotency key — once a result is stored for a job_id, subsequent enqueues with the same id are silently dropped for 24h. That's correct for one-shot gate approvals but broke multi-turn brief intake (every follow-up message was silently swallowed). Fix: `analyze_brief` now uses `{proposal_id}:analyze_brief:{user_msg.id}` as the job_id; gate approvals still use the bare `{proposal_id}:{phase}` form. `/retry` appends `uuid4()` so failed-phase retries actually re-run.

### 4. Research transparency (15 tasks, all executed via subagent-driven flow)

Goal: replace the silent 60–90s `run_research` / `run_benchmarks` phases with three visible chat messages per phase — pre-flight plan (Haiku) + live activity log (streaming, batched-flushed) + annotated findings (with inline hover-citation superscripts). Spec at `docs/superpowers/specs/2026-05-15-research-transparency-design.md`, plan at `docs/superpowers/plans/2026-05-15-research-transparency.md`.

Shipped (per commit list above):
- Backend infrastructure: `research_planner.py` (Haiku), `research_streaming.py` (`ActivityFlusher` + `process_stream`), `publish_message_updated` WS helper.
- `PipelineService.run_research` rewritten to orchestrate plan → activity log → streaming Opus 4.7 → findings.
- `PipelineService.run_benchmarks` mirrors run_research with Sonnet 4.6.
- Old `ResearchAgent`/`BenchmarkAgent` tests retired/migrated.
- New WS event type `message_updated` (carries the full updated message; frontend replaces by id).
- Four new frontend components: `<ResearchPlanCard />`, `<ResearchActivityLog />`, `<CitationPopover />`, `<ResearchFindingsCard />`.
- Citation rendering: inline hover superscripts injected via a post-render span-walk; sources list at the bottom.

**Two critical bugs the subagent reviewers caught that synthetic test fixtures hid:**

1. Anthropic web-search citations use `encrypted_index`, not `start_block_index`/`end_block_index`. My spec had the wrong field names; fix computes span offsets by matching `cited_text` against the body. **Without this fix, no citation superscripts would render in production despite green tests.** (`d7de977`)
2. `RESEARCH_SYSTEM` and `BENCHMARK_SYSTEM` are `str.format()` templates with placeholders like `{client_name}`. My plan passed them raw to `messages.stream` — Bedrock would receive literal `"# Client Research: {client_name}"` in the system prompt. (`27c77e0`, then mirrored in `13f38d7`)

Both fixes have regression tests asserting they can't reoccur silently.

---

## What's queued for the next session

### Option A — Execute the queued ideation plan (17 tasks)

**Spec:** `docs/superpowers/specs/2026-05-15-ideation-side-channel-design.md`
**Plan:** `docs/superpowers/plans/2026-05-15-ideation-side-channel.md`
**Status:** Both committed (`dc8a55f`, `8f694e7`). User approved. Not yet started.

V1 shape:
- One additive column on `chat_messages`: `channel: str` (default `"main"`, ideation messages have `"ideation"`).
- New `IdeationService.run_ideation` worker phase (separate class, read-only-by-construction).
- Two new API endpoints under `/chat/{id}/ideation/*`.
- One new frontend drawer (`<IdeationDrawer />`) + always-on `<IdeateButton />` in the proposal page header.
- Sonnet 4.6 hardcoded with `cache_control: ephemeral` on the proposal-context system block.
- No retry endpoint (ideation failures surface as inline error messages; user re-prompts).

Resume by invoking `superpowers:subagent-driven-development` and starting from Task 1.

### Option B — Live smoke test of research-transparency

We never ran the new research-transparency feature end-to-end against the real Bedrock + Postgres stack. Auto-tests pass; live behavior is unproven.

```bash
cd /Users/karthikramesh/Developer/nuprop
docker compose up --build -d
# wait for health
# in browser: register → create client → create proposal → drive brief intake → approve template gate
# watch worker logs for the new plan/activity_log/findings emit sequence
docker compose logs -f worker
```

Things to look for during the smoke test:
- Pre-flight plan card appears in the chat within ~1–2s of approving the template gate.
- Activity log card grows live with search queries and URLs being read (look for batched ~750ms updates via `message_updated` WS events).
- Findings card has citation superscripts inline; hover reveals popover with title + domain + cited snippet; sources list at the bottom.
- Activity log auto-collapses on completion.

If anything misbehaves (most likely on hover-citation rendering or the activity-log streaming), the relevant files are:
- Backend: `app/services/research_streaming.py`, `app/services/pipeline_service.py`
- Frontend: `frontend/src/components/chat/research-{plan-card,activity-log,findings-card}.tsx`

### Option C — Cleanup pass

Multiple code-review minor flags accumulated and were deliberately not addressed to keep momentum:
- Unused `pytest` import in `backend/tests/integration/test_research_planner.py`
- Unused `_FLUSH_MAX_INTERVAL_S` import in `backend/tests/integration/test_research_streaming.py`
- Inline `from app.services.ai.benchmark_agent import BENCHMARK_SYSTEM` in `pipeline_service.py:240` should move to top
- Hardcoded `max_searches` values (10 for research, 8 for benchmarks) could be module constants
- The post-Bedrock dead code: `app/services/ai/research_agent.py` and `app/services/ai/benchmark_agent.py` are no longer called from `PipelineService` (only their constants are imported). Could be deleted as a follow-up.
- Stale `ANTHROPIC_API_KEY=sk-ant-…` line in `.env.docker` (gitignored, harmless, but should be removed)

A single "cleanup pass" commit would knock these out.

---

## Deployment status

`fly.toml` is configured with the right `[processes]` block for app + worker. **Fly secrets are not set yet.** The user got partway through deploying (`d610572` fixed the `release_command`'s exec-form vs shell-form bug), but the deploy will fail at Alembic-migration time without secrets. Required:

```bash
fly secrets set -a nuprop \
  DATABASE_URL="postgresql+asyncpg://postgres:<pw>@<host>.supabase.co:5432/postgres" \
  REDIS_URL="redis://default:<token>@<host>.upstash.io:6379" \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id)" \
  AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key)" \
  AWS_REGION="ap-northeast-1"
```

Optional later: dedicated IAM user for the worker with Bedrock-only permissions instead of reusing the dev IAM user keys. Recipe is in this session's earlier discussion.

---

## Gotchas that are easy to forget

### Working directory drift
Bash commands persist `cwd` between calls in the harness. Many things assume `cwd = /Users/karthikramesh/Developer/nuprop` (repo root). Backend pytest needs `cd backend &&` first because `.venv/bin/python` lives in `backend/`. Frontend pnpm needs `cd frontend &&`. After git commands the cwd resets to the directory you `cd`'d INTO last — easy trap.

### Postgres uses VARCHAR(36), not native UUID
The Alembic initial migration created every ID/FK column as `VARCHAR(36)`. Earlier in this session we tried using native `PG_UUID` on Postgres and crashed on `operator does not exist: character varying = uuid`. The model now uses `String(36)` everywhere and `BaseRepository._coerce_id` always `str()`s. If you ever add a query that compares an ID column, **pass strings, not UUID objects**.

### ARQ behavior
- ARQ does **NOT** auto-retry on a bare `raise`. The worker's `_run_phase` shim was originally written assuming `raise` → ARQ retries — wrong. It now treats every exception as terminal: writes `pipeline_state.job_status.state = "failed"`, emits a `pipeline_error` WS event, and returns. User retries via the `POST /chat/{id}/retry` endpoint.
- `_job_id` is an idempotency key. For multi-turn brief intake the job_id includes the `user_msg.id` so each turn is a fresh job. For one-shot gate approvals (template/cost_model/narrative) the job_id is bare `{proposal_id}:{phase}` to prevent double-clicks.

### Bedrock model IDs (verified, not guessed)
```
Heavy    : global.anthropic.claude-opus-4-7
Balanced : global.anthropic.claude-sonnet-4-6        (NOT -v1)
Fast     : global.anthropic.claude-haiku-4-5-20251001-v1:0
```
Verified via `aws bedrock list-inference-profiles --region ap-northeast-1`.

### Opus 4.7 constraints
- Do **not** pass `temperature`, `top_p`, or `top_k` — returns 400. `AIService._build_kwargs` strips these automatically when `tier == Tier.HEAVY`.
- Extended thinking only supports `thinking={"type": "adaptive"}`. Old `{type: enabled, budget_tokens}` returns 400.

### `_no_network` test guard
`backend/tests/conftest.py:_no_network` patches `AnthropicClient.complete`/`.complete_json`/`.stream`/`.is_configured` to fail loudly on accidental real API calls. After the Bedrock migration, `is_configured` is always `True` in production (auth happens at call time); the guard explicitly monkeypatches it back to `False` during tests so AI agents take their non-LLM fallback paths.

### WebSocket event types
- `new_message` — a fresh chat message is being added to the thread.
- `message_updated` — **NEW** in this session. An existing message's full state has changed (e.g., the activity log got more events). Frontend looks up by id and replaces.
- `typing` — typing-indicator toggle.
- `phase_change` — pipeline_state.current_phase changed.
- `progress` — per-phase progress event (used by phases that DON'T have a structured activity log: cost_model, narrative, outputs).
- `pipeline_error` — terminal failure of a phase.

### Channel-by-message routing on the frontend
The frontend's `chat-store` has only one `messages` slice today. **When ideation lands** (Option A), it'll add a parallel `ideationMessages` slice and route incoming WS messages by their `channel` field. The store's `updateMessage` (added today) only operates on `messages` for now; will need to be channel-aware then.

---

## How to resume

1. Read this file end-to-end (~5 min).
2. Check `git log --oneline -20` and `git status` to confirm state matches what's documented here.
3. Look at the project memory for additional context that didn't fit here:
   ```
   ~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md
   ```
4. Ask the user: **"You have two queued items: execute the ideation plan, or live-smoke-test the research-transparency build. Which first?"**

If they pick ideation execution: invoke `superpowers:subagent-driven-development` and start from Task 1 of `docs/superpowers/plans/2026-05-15-ideation-side-channel.md`. The plan was approved before being queued; don't re-design.

If they pick the smoke test: bring up the stack with `docker compose up --build -d` and walk them through driving a proposal through the brief → template approval → research → benchmarks gate. Watch `docker compose logs -f worker` for the new plan/activity_log/findings emit sequence.

If they want neither: do Option C (cleanup pass) or ask what they want.
