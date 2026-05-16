# NUPROP Session Handoff

**Last updated:** 2026-05-16 (mid-day rewrite — auto-deploy enabled + M16-M20 truth baseline)
**Latest commit on `main`:** `9194bd0` (pushed to `origin/main`)
**Working tree:** clean. Branch: `main`. No worktrees.
**Production:** **LIVE at https://nuprop.fly.dev** — `GET /api/v1/health → 200`. **Auto-deploys on push to `main`** (GitHub Actions, `FLY_API_TOKEN` secret set).

> ⚠️ **Earlier versions of this file claimed M16-M20 were unstarted.** That was wrong. M16-M20 are substantially scaffolded at the backend — see `docs/superpowers/audits/2026-05-16-m16-m20-state-audit.md` for the full audit. The "Next session" menu below is updated to reflect actual state.

> Read this top-to-bottom (~3 min) on resume. The "Quick verification" block at the bottom gets you from `/clear` to "ready to keep working" in 60 seconds of bash.

---

## TL;DR

Today shipped two big things and closed the entire session backlog:

1. **Ideation side-channel** — the 17-task plan from 2026-05-15 executed via `superpowers:subagent-driven-development`. A read-only Claude side-channel attached to every proposal, with its own drawer, channel-aware store routing, channel-scoped typing indicator, error rendering, and isolated worker-failure handling. Merged to `main` cleanly.
2. **Production deploy** — NUPROP is now live at https://nuprop.fly.dev on Fly Mumbai, with Neon Postgres (us-east-1) and Upstash Redis. All 6 secrets deployed, app + worker machines healthy, frontend served, health check passing.

Plus four follow-ups landed: register-flow React #31 fix, three reviewer follow-ups (test-helper consolidation, O(n²)→O(n) hydration, channel-aware typing), and the brief-intake-on-Haiku tier switch from a prior session.

**On the menu for the next session:** the older PRD backlog (M16-M20: client context + connector trio), GitHub Actions auto-deploy wire-up, dedicated AWS IAM user for Bedrock-only access. No bugs, no open work, no uncommitted state.

---

## Quick verification (run this first on resume)

```bash
# 1. Repo state
cd /Users/karthikramesh/Developer/nuprop
git log --oneline -3                       # HEAD = 1bc818c (or later)
git status                                 # nothing to commit, working tree clean

# 2. Local test suites
cd backend && .venv/bin/python -m pytest -q   # → 244 passed, 0 skipped
cd ../frontend && pnpm test --run              # → 131 passed across 24 files

# 3. Production health
curl -s https://nuprop.fly.dev/api/v1/health
# → {"status":"ok","service":"nuprop"}

# 4. Fly machines (3 expected: 1 app started, 1 worker started, 1 worker stopped-standby)
fly machines list -a nuprop
```

If all four pass, you're current. Pick from the menu in "Next session" below.

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
| Fly deploy config | `fly.toml` (secrets set out-of-band; live values via `fly secrets list -a nuprop`) |
| GH Actions deploy workflow (currently disabled) | `.github/workflows/deploy.yml` |

---

## What's on the wire (production stack)

```
Browser → https://nuprop.fly.dev
            │
            ▼
       Fly Edge (TLS, /api/v1/health probe every 30s)
            │
            ▼
       App machine (Fly bom / Mumbai, shared-cpu-2x 1GB)
       ├─ uvicorn app.main:app on port 8080
       ├─ /data volume (PDF/DOCX outputs)
       ├─ /root/.aws mount NOT used (boto3 uses env vars)
       └─ env: DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, AWS_*
            │
            ├──→ Neon Postgres (us-east-1, ~200ms RTT)
            │    - postgresql+asyncpg://...neon.tech/neondb?ssl=require
            │    - Free tier, 0.5GB, scales to zero
            │    - Migration 02_ideation_channel applied
            │
            ├──→ Upstash Redis (regional plan, ~30ms RTT)
            │    - rediss://default:...@positive-man-126512.upstash.io:6379
            │    - TLS REQUIRED — plain redis:// is rejected
            │    - Used by ARQ jobs + WS pub/sub bridge
            │
            └──→ AWS Bedrock (ap-northeast-1 / Tokyo)
                 - via personal IAM user `karthik` (account 809644065208)
                 - Sonnet 4.6 default, Opus 4.7 research, Haiku 4.5 brief-intake + ideation-plan

       Worker machine (Fly bom, 1 active + 1 standby, shared-cpu-2x 1GB)
       └─ arq app.workers.pipeline.WorkerSettings
          - 7 phases: analyze_brief, run_research, run_benchmarks,
                      build_cost_model, generate_narrative, generate_outputs,
                      run_ideation
          - Connects to same Redis + Postgres + Bedrock
```

**Fly Mumbai → Neon us-east-1 is the one obvious slow seam** — every query pays ~200ms. Tolerable for an LLM-bound app (Bedrock calls dominate 5-10s of latency anyway). Neon's branching makes a region migration cheap if it ever becomes a problem.

---

## Repo state at handoff

```text
origin/main = 1bc818c = local main = clean working tree
```

Recent history (newest first — top 17 are this session):

```
1bc818c docs: nuprop is live — production deploy succeeded + trap notes
f6bd173 docs: capture partial production-deploy state (paused on DB+Redis decisions)
c1794d8 docs: mark loose-ends cleanup (Option B) complete
1b8645c docs: mark all three reviewer follow-ups complete
dbd081c feat(ui): channel-aware typing indicator for the ideation drawer
070b4e1 perf(ui): O(n) ideation hydration via mergeIdeationMessages store action
6a51d69 test: consolidate _make_proposal helpers into shared fixtures
0ef10dd feat: switch brief_analyzer to Haiku 4.5 for chat felt-latency
c47ebf1 docs: record formatApiError fix, correct bug-#1 misattribution + ignore .playwright-mcp
b363d6f fix(ui): formatApiError handles Pydantic 422 array detail (React #31 crash)
6d10990 docs: record smoke-test results + flag two register-flow bugs
a38bdd1 docs: refresh handoff for ideation side-channel merge
91bb135 fix: ideation real-time error delivery, typing isolation, migration safety
5b82c89 feat(ui): mount IdeateButton and IdeationDrawer on the proposal page
58b8638 feat(ui): IdeateButton with URL hash sync
e3b2c16 feat(ui): IdeationDrawer with empty state, message list, send, and error rendering
fdcb491 feat(api): useIdeationMessages and useSendIdeationMessage hooks
… (12 more ideation-build commits)
97472da docs: session handoff for resume after /clear     (← session boundary)
```

### Test suites (verified at end of session)

```bash
cd backend && .venv/bin/python -m pytest -q
# → 244 passed, 0 skipped  (was 224 at session start; +20 ideation tests)

cd frontend && pnpm test --run
# → 131 passed across 24 files  (was 101 at session start; +30 across ideation, formatApiError,
#                                 mergeIdeationMessages, channel-typing, and WS-routing)

cd frontend && pnpm build
# → clean

.venv/bin/python -c "from app.main import app; print(len(app.routes))"
# → 64   (was 62; +2 ideation routes — same as the 2026-05-15 merge)
```

---

## Today's arc, in order

1. **Resume + decide** — started on `97472da`, picked Option A (execute the ideation plan).
2. **Worktree setup** — `EnterWorktree(name: ideation-side-channel)`, symlinked backend/.venv + frontend/node_modules from main checkout, verified baseline (224 backend / 101 frontend).
3. **Ideation execution** — 16 of 17 tasks via subagent-driven-development. Each task: implementer subagent (Haiku for mechanical, Sonnet for integration) → spec-compliance reviewer (Haiku) → code-quality reviewer (Sonnet for non-trivial) → fix loop → commit. Per-task commits amended for clean atomic history.
4. **Operational recovery** — Task 12's implementer accidentally committed to `main` instead of the worktree branch (subagent ran `cd /Users/karthikramesh/Developer/nuprop/frontend`, the MAIN checkout, not the worktree's). Caught via the test count going 104→103 instead of 106. Cherry-picked to worktree, `git reset --hard 97472da` on main, brief_analyzer change stashed/popped to survive. Defensive prompt preamble added to every subsequent frontend-task subagent. No further contamination.
5. **Cross-cutting final review** — caught two Critical bugs the per-task reviews missed: worker error path didn't publish `new_message` (drawer wouldn't render Bedrock failures in real time); shared `isTyping` flag leaked the ideation typing event into the main chat panel. Both fixed in `91bb135`.
6. **Worktree merge** — fast-forward merge to main, ExitWorktree(remove). 16 commits landed cleanly.
7. **Refresh HANDOFF.md** — initial post-merge version (`a38bdd1`).
8. **Smoke test (Task 17)** — `docker compose up --build -d` against fresh build, Playwright drove register → create proposal → open drawer → send → verify everything end-to-end against real Bedrock. Caught two pre-existing frontend bugs in the process (`.local` TLD rejection — actually correct behavior; React #31 crash on rendering Pydantic 422 array — real bug).
9. **formatApiError fix** (`b363d6f`) — helper in `frontend/src/api/client.ts` that returns a string from any axios-error shape. Applied at both crash sites. 5 vitest cases.
10. **brief_analyzer Haiku switch** (`0ef10dd`) — committed the loose change from a prior session.
11. **Three reviewer follow-ups** — `_make_proposal` consolidation (`6a51d69`), O(n) hydration (`070b4e1`), channel-aware typing (`dbd081c`).
12. **Loose ends cleanup (Option B)** — deleted the duplicate `fly-deploy.yml` (Fly's auto-on-push template), kept the existing `deploy.yml` placeholder with auto-deploy commented out.
13. **Production deploy** — provisioned Neon (us-east-1 free tier) + Upstash (regional plan, free tier), staged 6 secrets, did 3 deploys (first failed on Redis TLS; second got tangled in lease handling; third forced full replacement and came up clean). Live at https://nuprop.fly.dev as of `1bc818c`.

**One session, 22 commits on `main`, full feature shipped + verified + deployed.**

---

## Next session — pick one

### Option A — Wire up GitHub Actions auto-deploy ✅ DONE 2026-05-16

`FLY_API_TOKEN` GH secret set, `.github/workflows/deploy.yml` uncommented (`push: branches: [main]` active, `workflow_dispatch:` kept for manual re-deploys). First auto-deploy run `25965414713` succeeded in 2m14s. Every push to `main` now redeploys prod.

### Option B — Finish M16-M20 (the REAL state)

**M16-M20 are ~60% built, 40% remaining.** The 40% is the hardest 40%: backend hardening (5 CRITICAL security issues), frontend UI completion (Drive/Calendar/Slack have no React Query hooks, no Slack callback route, zero tests for any of this surface), pipeline integration (only 1 of 7 phases consumes M16-M20 data), and production OAuth wiring (5 missing Fly secrets + 2 unregistered OAuth apps).

**Full audit:** `docs/superpowers/audits/2026-05-16-m16-m20-state-audit.md` — read this before touching M16-M20 code.

**Slicing strategy (S0 → S6, ~5-8 dev-days + ~1hr of user OAuth-console clicks):**

| Slice | Estimate | What ships |
|---|---|---|
| ~~S0~~ — Truth baseline | ~~0.25d~~ ✅ done 2026-05-16 | This handoff rewrite + audit doc + memory |
| **S1** — Backend CRITICAL fixes | 1d | Fail-loud encryption, OAuth CSRF, module-level logging, DI for services, narrowed excepts |
| **S2** — Manual context UI on Client page | 1d | M16 shippable end-to-end |
| **S3** — Connector frontend + Slack callback + tests | 1.5d | M17-M19 frontend parity |
| **S4** — Production OAuth wiring | 0.5d | Google + Slack OAuth apps registered, secrets set, smoke-tested |
| **S5** — Pipeline integration | 1.5d | Wire context_brief into 5 unwired phases; `build_cost_model` consumes `proposal.preferences`; ideation gets relationship context; email auto-enrichment post-sync |
| **S6** — Backend HIGH/MEDIUM polish + retry/backoff | 1d | Defer-able |

Each slice gets its own spec in `docs/superpowers/specs/`, its own worktree, and a user-approval checkpoint at the end. **Active slice: S1** (in worktree `m16-m20-s1-backend-hardening`).

### Option C — Production hardening

- **Dedicated AWS IAM user** — currently NUPROP runs against the `karthik` personal account's keys. Create `nuprop-bedrock-prod` IAM user with `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on the three Sonnet/Opus/Haiku model ARNs, generate keys, rotate Fly secrets. ~15 min.
- **Neon region migration** — currently us-east-1; ~200ms RTT from Fly Mumbai. Recreate in Singapore (`ap-southeast-1`) for ~30ms RTT, use Neon's branching to migrate without downtime. ~20 min.
- **CLAUDE.md note about `.local` TLD** — the email validator rejects it. Add to the project's developer notes so future testers default to `@example.com`. ~1 min.

---

## Architecture quick-reference (don't relearn these)

### Ideation side-channel design

- `IdeationService.run_ideation` is **read-only by construction** — instantiates `ProposalRepository` but never calls `update`. Two tests assert this with before/after fingerprints (`test_run_ideation_does_not_mutate_proposal_fields`, `test_run_ideation_task_does_not_touch_pipeline_state`).
- The worker's `_run_ideation_phase` handles its own try/except, does NOT call `_set_job_status` (that touches `pipeline_state` which is reserved for the main pipeline). On failure: writes a `system/error` chat row to the ideation channel AND publishes a `new_message` event (so the drawer renders the error in real time) AND a `pipeline_error` event (observability).
- **Commit-before-broadcast** is the architectural invariant from the 2026-05-15 worker rewrite. Test `test_run_ideation_commits_before_broadcasting` installs a spy on `publish` that opens a fresh session inside the callback and asserts the row is already visible — if anyone reorders the commit and the publish, this test fails immediately.
- The system prompt has prompt-caching enabled via `cache_control: {"type": "ephemeral"}` on the proposal-context block. For a developed proposal it can hit 6-8k tokens; turn 2+ gets ~85% input-token cost reduction and ~1s faster TTFT.

### Frontend store routing

- `messages` and `ideationMessages` are two parallel slices. **Both** `addMessage` and `updateMessage` route by `msg.channel === 'ideation'`. Same for `mergeIdeationMessages` (O(n) batch dedup added today; used by drawer hydration).
- `isTyping` and `isIdeationTyping` are two independent scalars. WS `typing` events route by `data.channel` (defaults to `'main'` when omitted — back-compat). `new_message` arrival clears the typing flag for its own channel.
- `setMessages` is main-channel-only by design (used by initial hydration of the main pipeline).

### Worker / WS plumbing

- Ideation enqueues with idempotency key `{proposal_id}:run_ideation:{user_msg.id}` — every user turn is a fresh ARQ job (no idempotent dropping).
- Main pipeline gates use the bare `{proposal_id}:{phase}` form to prevent double-clicks.
- `ws_publish_spy` fixture in conftest patches `publish` in three places: `events.publish`, `pipeline_service.publish`, AND `ideation_service.publish`. Without the third, ideation-side tests opted into the spy would get unintercepted publishes.

### WS event types

- `new_message` — fresh chat message; carries `channel` field; frontend routes by `channel`.
- `message_updated` — existing message's full state changed; **also** routes by channel (Task 13 fix).
- `typing` — typing-indicator toggle. **NEW today:** carries optional `channel` field; routes between `isTyping` and `isIdeationTyping`.
- `phase_change` — main pipeline's `current_phase` changed. Ideation does NOT emit this.
- `progress` — per-phase progress for phases without structured activity logs (cost_model, narrative, outputs).
- `pipeline_error` — terminal phase failure. **NEW today:** ideation emits `phase: "ideation"` (not `"run_ideation"` — the function name). Frontend's `use-websocket.ts` has a `console.warn` handler. The user-facing error message arrives as a separate `new_message` with `role=system, extra_data.kind="error"`.

---

## Gotchas that are easy to forget

### Production deploy traps (NEW today)

- **Upstash requires TLS.** REDIS_URL must use `rediss://` (two s's). Plain `redis://` opens TCP but Upstash drops the connection server-side. Symptom: `redis.exceptions.ConnectionError: Connection closed by server` and the FastAPI lifespan exits with code 3.
- **asyncpg uses `?ssl=require`, NOT `?sslmode=require`.** SQLAlchemy's asyncpg dialect doesn't translate the libpq-form. The Neon URL pasted from their dashboard uses `?sslmode=require` (and gets shortened to `?sslmode=req` in their UI for some reason); rewrite it.
- **A crash-looping Fly machine holds its lease.** While the app is in a startup crash loop, `fly secrets set` cannot acquire the machine's lease to apply new secrets. If you're stuck: kill the running `fly deploy` first, then re-stage and re-deploy.
- **`fly secrets deploy` refuses if no machine is in a "deployed" state.** After cancelling a failed deploy, only full `fly deploy` (not the cheaper `fly secrets deploy`) can apply new secrets.
- **Rolling deploys leave the failed machine on the OLD image** when its lease can't be acquired. Force a full replacement with a fresh `fly deploy` after the lease conflict clears.

### Worktree subagent contamination

- Bash `cwd` persists between calls. If a frontend-task subagent runs `cd /Users/karthikramesh/Developer/nuprop/frontend` instead of `cd .../.claude/worktrees/<branch>/frontend`, every subsequent file write goes to the MAIN checkout. Commits land on `main`, not the worktree branch.
- Mitigation that worked: every subagent prompt prefixed with — "ALWAYS prefix `cd frontend && ...` with the FULL worktree path. Before commit, run `git branch --show-current` and confirm. If `main`, STOP and report BLOCKED."
- Detection: implementer's test count comes back wrong (e.g., 103 instead of 106 because the main checkout lacks the worktree's prior tasks).
- Recovery: cherry-pick the misplaced commit to the worktree, `git stash` any unrelated working-tree changes on main, `git reset --hard <pre-mistake>`, restore stash.

### Postgres uses VARCHAR(36), not native UUID
Unchanged across sessions. Pass strings, not UUID objects, to anything that compares ID columns. `BaseRepository._coerce_id` always `str()`s.

### ARQ behavior
Bare `raise` does NOT auto-retry. Both `_run_phase` (main pipeline) and `_run_ideation_phase` (ideation) treat every exception as terminal — write a failure marker, emit a WS event, return cleanly so ARQ marks the job done.

### Bedrock model IDs (verified)
```
Heavy    : global.anthropic.claude-opus-4-7
Balanced : global.anthropic.claude-sonnet-4-6        (NOT -v1)
Fast     : global.anthropic.claude-haiku-4-5-20251001-v1:0
```
Ideation uses `Tier.BALANCED` (Sonnet 4.6). Brief intake now uses `Tier.FAST` (Haiku 4.5) as of `0ef10dd`.

### Opus 4.7 constraints
No `temperature`/`top_p`/`top_k`. `thinking={"type": "adaptive"}` only. `AIService._build_kwargs` strips these when `tier == Tier.HEAVY`. If anything ever flips ideation from BALANCED to HEAVY, also strip `temperature=0.7` from the `messages_create` call — see the inline comment in `ideation_service.py`.

### Email validator footgun
The Pydantic `EmailStr` rejects `.local` TLD ("the part after the @-sign is a special-use or reserved name"). For local smoke testing, use `@example.com` / `@example.test` / `@example.org`.

### `_no_network` test guard
`backend/tests/conftest.py:_no_network` patches `AnthropicClient.complete/.complete_json/.stream/.is_configured` so accidental real API calls fail loudly. Tests that exercise an AI path monkeypatch the service method or `get_ai_service` directly — those patches apply after the autouse guard and win.

---

## How to resume next session

1. Read this file end-to-end (~3 min).
2. Run the "Quick verification" block above. All four checks should pass.
3. `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/session_handoff_2026_05_16.md` is the in-memory pointer to this doc and contains the same quick-verification block.
4. Pick from "Next session" above:
   - **A (auto-deploy)** if you want to remove the manual `fly deploy` step.
   - **B (M16 or the connector trio)** for product progress.
   - **C (production hardening)** for the security/perf knobs.
5. The codebase is in its cleanest state in weeks. No bugs, no open work, no uncommitted state, all tests green, production live.
