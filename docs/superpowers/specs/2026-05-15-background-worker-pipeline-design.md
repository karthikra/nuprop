# Design: Background-worker proposal pipeline

**Date:** 2026-05-15
**Status:** Approved (design) — pending spec review
**Area:** `backend/` — proposal generation pipeline

## Context

NUPROP turns a client brief into a proposal through a multi-phase AI pipeline
(brief analysis → template → research → benchmarks → cost model → narrative →
output generation). Today the entire downstream pipeline runs **synchronously
inside a single HTTP request**:

- `get_db()` opens one `AsyncSession` per request and commits **once**, after the
  route handler returns (`backend/app/infrastructure/db/database.py:42`).
- `ChatViewModel.approve_gate()` and `send_message()` run the whole pipeline for a
  gate inside that one request — each phase calling Claude (~30–90s) — and emit
  `phase_change` / `progress` / `new_message` **WebSocket broadcasts mid-pipeline**
  (`backend/app/viewmodels/chat_viewmodel.py`).
- None of the `proposal_repo.update(...)` writes are committed yet. A client that
  reacts to a "phase done" WS event with a fresh REST request reads the
  **pre-pipeline** row — a read-your-writes violation across sessions. On SQLite a
  second connection cannot see another connection's uncommitted writes at all.

The reliable copy of phase output currently lives only in chat messages'
`extra_data` (carried inline in the WS payload), which is why
`_generate_outputs()` has a fallback reading narrative content from the last
narrative message (`chat_viewmodel.py:496-503`).

This bug is tracked by the skipped test
`backend/tests/integration/test_persistence_bug.py`.

## Goals

- Each pipeline phase runs as a **durable, retryable background job** with its own
  DB session that **commits before it broadcasts**. After this change, a REST read
  triggered by a WS event always observes committed data.
- The long pipeline no longer blocks the HTTP request; gate-approval requests
  return an immediate acknowledgement.
- Phase failures are visible (`pipeline_state.job_status`) and retried; a stuck
  pipeline is detectable by the UI.
- The `extra_data` fallback in `_generate_outputs()` becomes unnecessary.

## Non-goals

- No change to the AI services themselves (`research_agent`, `narrative_generator`,
  etc.) — only *where* and *in what session* they run.
- No horizontal scaling of the API process. One API process + one worker process.
- No change to the proposal pipeline's phase sequence or the 3 user-approval gates.

## Decisions (approved)

| Decision | Choice |
|---|---|
| Queue library | **ARQ** — async-native, Redis-only, retries + deferred jobs built in |
| Job granularity | **Per-phase** jobs (6 types) — clean per-phase retry semantics |
| Redis | **Required infrastructure** — added to `docker-compose.yml`; no synchronous in-line fallback (that path would still have the bug) |

## Architecture

```
  HTTP request                ARQ worker process              Redis
  ────────────                ──────────────────              ─────
  approve_gate()                                          ┌─► jobs queue
   ├─ validate + ownership                                │
   ├─ update pipeline_state ──┐                           │
   ├─ create ack message      │ committed by get_db()     │
   ├─ enqueue first phase ────┼──────────────────────────►┘
   └─ return ack message      │
                              │   run_research(ctx, id)
                              │    ├─ own AsyncSession
                              │    ├─ ResearchAgent → proposal.research
                              │    ├─ COMMIT                ┌─► nuprop:ws
                              │    ├─ events.publish ──────►┤   pub/sub
                              │    └─ enqueue run_benchmarks┘
                              │
  API process                 │
  ┌─ ws subscriber (lifespan) ◄┘  receives {proposal_id, payload}
  │   └─ ws_manager.broadcast(proposal_id, payload) ──► browser WebSocket
```

### New components

| Path | Responsibility |
|---|---|
| `app/infrastructure/queue/redis.py` | ARQ `RedisSettings` from `Settings`; `get_arq_pool()` (lazy pooled connection used by the API process to enqueue) and lifecycle helpers. |
| `app/infrastructure/queue/events.py` | `publish(proposal_id, payload)` — push a WS event onto Redis channel `nuprop:ws`. `ws_event_subscriber()` — async loop the API process runs (started in `lifespan`) that receives events and calls `ws_manager.broadcast`. |
| `app/workers/pipeline.py` | The 6 ARQ task functions + `WorkerSettings` (the `arq` worker entrypoint). Thin — each task opens a session, calls a `PipelineService` method, handles retry/failure bookkeeping. |
| `app/services/pipeline_service.py` | The pipeline logic **extracted from `ChatViewModel`**. Constructed with any `AsyncSession`. One method per phase. Owns `_merge_preferences_into_config` (moved from `ChatViewModel`). |

### Modified components

| Path | Change |
|---|---|
| `app/viewmodels/chat_viewmodel.py` | Slims from ~830 lines to ~250. Loses `_run_research_and_benchmarks`, `_build_cost_model`, `_generate_narrative`, `_generate_outputs`, `_broadcast_progress`, `_merge_preferences_into_config` (all → `PipelineService`). `send_message` / `approve_gate` become: validate → update `pipeline_state` → create ack message → enqueue first phase job → return. The `brief` gate stays fully synchronous (template matching is instant keyword scoring, no LLM). |
| `app/core/config.py` | Redis settings already exist (`REDIS_URL`). Add ARQ-specific knobs if needed (`ARQ_MAX_TRIES` default 3). |
| `app/main.py` | `lifespan` starts the `ws_event_subscriber()` task and the ARQ pool; closes both on shutdown. |
| `app/core/ws_manager.py` | Unchanged — still owns local connections. All emit sites switch from `ws_manager.broadcast(...)` to `events.publish(...)`. |
| `app/views/v1/chat.py` | `send_message` response shrinks to `[user_msg]` (assistant reply now arrives via WS). `approve_gate` still returns the ack `ChatMessageResponse`. |
| `pyproject.toml` | Add `arq` dependency. |
| `docker-compose.yml` | Add `redis` service and a `worker` service (`arq app.workers.pipeline.WorkerSettings`). |
| `fly.toml` | Add a `[processes]` block: `app` (uvicorn) + `worker` (arq). `REDIS_URL` → Upstash in prod. |

## Phase jobs

Six ARQ task types. Each task: mark `job_status` running → call the matching
`PipelineService` method (own session, commits internally) → on success mark
`job_status` complete and enqueue the next phase (if any) → on exception, retry;
after `ARQ_MAX_TRIES` mark `job_status` failed and publish an error event.

| Job | Triggered by | Work | Next |
|---|---|---|---|
| `analyze_brief` | `send_message` (brief phase) | `BriefAnalyzer`; on completion writes `proposal.brief`, creates a `brief_summary` (or follow-up question) message | — (waits for user) |
| `run_research` | `approve_gate("template")` | `ResearchAgent` → `proposal.research`; commit; progress events | `run_benchmarks` |
| `run_benchmarks` | chained | `BenchmarkAgent` → `proposal.benchmarks`; commit; creates combined `research_findings` message; advances `pipeline_state` to `cost_model_review` | `build_cost_model` |
| `build_cost_model` | chained | `CostModelBuilder` → `proposal.cost_model`; commit; creates `cost_model` message | — (waits for user) |
| `generate_narrative` | `approve_gate("cost_model")` | `NarrativeGenerator` → narrative fields; commit; advances to `narrative_review`; creates `narrative_preview` message | — (waits for user) |
| `generate_outputs` | `approve_gate("narrative")` | `DocumentGenerator` + `SiteGenerator` → file paths + `status`; commit; advances to `complete`; creates `output_ready` message | — (done) |

**Commit-before-broadcast rule:** within every phase the DB `commit()` happens
*before* the corresponding `events.publish(...)`. This is the fix.

## Data flow & state

`proposal.pipeline_state` gains a `job_status` key:

```json
{
  "current_phase": "research",
  "phases_completed": ["brief", "template_confirm"],
  "job_status": {
    "phase": "run_research",
    "state": "queued | running | complete | failed",
    "error": null,
    "updated_at": "2026-05-15T..."
  }
}
```

- `approve_gate` sets `state: queued` synchronously when it enqueues.
- The task sets `running` at start, `complete` at end.
- After retries are exhausted the task sets `failed` + `error` and publishes a
  `pipeline_error` WS event; the UI can surface a retry affordance (a `POST
  /chat/{id}/retry` endpoint re-enqueues the failed phase — included in scope).

## WebSocket bridge

Because the worker is a **separate process**, it cannot reach the API process's
in-memory `ws_manager` connections. All WS emits go through Redis pub/sub:

- Emit side (`events.publish`): `redis.publish("nuprop:ws", json({proposal_id, payload}))`.
- Receive side (`ws_event_subscriber`, one per API process, started in `lifespan`):
  subscribes to `nuprop:ws`, and for each message calls
  `ws_manager.broadcast(proposal_id, payload)` for connections it holds locally.
- The API process both publishes and subscribes — its own ack/typing emits make a
  sub-millisecond round-trip through local Redis. One uniform code path; the small
  added latency is acceptable and keeps the design simple.

## Idempotency

- Phase field writes (`proposal.research`, `.cost_model`, …) are overwrites — safe
  to re-run on retry.
- Enqueue calls pass a deterministic `_job_id` of `f"{proposal_id}:{phase}"` so a
  double-enqueue is de-duplicated by ARQ.
- Chat-message creation happens once, at the *end* of a successful task. A crash
  in the narrow window between commit and ARQ marking the job done could produce
  one duplicate message on retry; the frontend chat store already dedupes by
  message id for WS delivery, and this is an accepted rare edge — deterministic
  message keys can harden it later if needed.

## Frontend touchpoint

`POST /chat/:id/send` currently returns `[user_msg, assistant_msg]`. With brief
analysis queued, it returns `[user_msg]` only — the assistant reply arrives over
the existing WebSocket channel, which the chat store already handles and dedupes.
Change is confined to `frontend/src/api/proposals.ts` (the `useSendMessage` return
type) and any caller that read `[1]` from the response (`builder.tsx`). The
approve-gate flow is unaffected — `approval-gate.tsx` already only checks for HTTP
success and relies on WS for subsequent messages.

## Testing

No live Redis is needed in the test suite:

- **`test_persistence_bug.py`** — rewritten from a `skip` into a real passing test.
  Run a phase function (e.g. `PipelineService.run_research`) against the test DB,
  then assert the written field is visible from a **separate** session — proving
  the per-phase commit.
- **`test_pipeline_service.py`** (new, unit/integration) — each `PipelineService`
  method against a real test session: correct fields written and committed,
  `pipeline_state` advanced, the right message type created. AI services
  monkeypatched (same pattern as the existing `test_chat_api.py` AI-path test).
- **`test_pipeline_worker.py`** (new) — the ARQ task functions: `job_status`
  transitions (`queued`→`running`→`complete`), next-phase enqueue is called, and
  the retry-to-`failed` path. ARQ context + redis are faked/mocked.
- **`test_chat_api.py`** — updated: `approve_gate` creates the ack message and
  calls `enqueue_job` (mocked pool); it no longer runs the pipeline inline.
- **WS bridge** — `events.publish` + `ws_event_subscriber` tested with a fake
  pub/sub that round-trips a payload to a stub `ws_manager`.
- `conftest.py` — add a fixture that provides a mocked ARQ pool / `enqueue_job`
  spy, and stubs `events.publish` to a collectible list so tests can assert emitted
  events without Redis.

## Rollout / deployment notes

- `arq` added to backend deps; `uv` lock regenerated.
- `docker-compose.yml`: `redis` service + `worker` service sharing the app image
  with command `arq app.workers.pipeline.WorkerSettings`.
- `fly.toml`: `[processes]` with `app` and `worker`; provision Upstash Redis and
  set `REDIS_URL`. (Deploy is still gated — the GitHub Actions workflow remains
  disabled until Fly.io is configured.)
- No DB migration: `job_status` lives inside the existing `pipeline_state` JSON
  column.

## Out of scope / follow-ups

- Multi-instance API fan-out (would need every API instance subscribed — already
  works since each subscribes to `nuprop:ws`, but untested at scale).
- Deterministic message keys for exact-once message creation.
- A dead-letter queue / admin view for permanently-failed jobs.
