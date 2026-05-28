# Sub-Slice 3: Visible Progress UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`). Every implementer MUST run the worktree+branch safety check before committing (see "Commit safety").

**Goal:** Surface "what's happening" during pipeline phases. (P9) Broadcast `job_status` transitions over WebSocket and render a sticky top-of-chat **PhaseProgress** widget showing the current phase, its state (queued/running/complete/failed), elapsed time, and any error. (P10) Give failed phases a **Retry** button wired to the existing `POST /chat/{id}/retry`.

**Architecture:** The backend already persists `job_status` in `pipeline_state` but never broadcasts it. We add a `job_status` WS event: emitted from the worker (`_run_phase`, via the Redis `publish` bridge) for running/complete/failed, and from the API process (re_run_phase dispatch + retry endpoint) for queued. The frontend gains a `jobStatus` store slice fed by a new WS handler, a `PhaseProgress` component pinned at the top of the chat scroll area, and a retry mutation surfaced on the failed state.

**Tech Stack:** Backend — FastAPI, ARQ, Redis pub/sub (`app/infrastructure/queue/events.py::publish`). Frontend — React 18 + TypeScript, Zustand (`chat-store`), TanStack Query, Tailwind, Vitest.

**Source spec:** `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md` items P9, P10. **Locked decision (user, 2026-05-28):** Option A — add the backend `job_status` WS broadcast + a sticky top-of-chat widget (not frontend-only derivation, not folding into PipelineSidebar).

---

## Commit safety (every implementer subagent MUST do this)
A prior subagent accidentally committed to `main`. Before ANY `git commit`:
```
git rev-parse --show-toplevel    # MUST end with /.claude/worktrees/post-s10-stability-and-chat-intent
git branch --show-current        # MUST be: worktree-post-s10-stability-and-chat-intent
```
STOP/report BLOCKED if either fails. NEVER run git against `/Users/karthikramesh/Developer/nuprop`. Stage explicit paths only.

---

## The `job_status` WS event contract (locked — both ends agree on this)
```json
{ "type": "job_status", "phase": "run_research", "state": "running", "error": null, "updated_at": "2026-05-28T10:00:00+00:00" }
```
- `phase`: the ARQ job name (e.g. `run_research`, `run_benchmarks`, `build_cost_model`, `generate_sections`, `analyze_brief`). This matches what `pipeline_state.job_status.phase` already stores and what `POST /chat/{id}/retry` reads.
- `state`: one of `queued` | `running` | `complete` | `failed`.
- `error`: string on `failed`, else null/absent.
- `updated_at`: ISO-8601 server timestamp (the widget uses it as the elapsed-time anchor while `running`).

---

## Shared facts (verified against current code)
- **Worker** `backend/app/workers/pipeline.py`: `_run_phase` calls `_set_job_status(session, proposal_id, phase, state, error=None)` three times — `"running"` (line ~58), `"failed"` (line ~67), `"complete"` (line ~74). `_set_job_status` builds `pipeline["job_status"] = {"phase","state","error","updated_at"}` and persists. The worker already does `await publish(ctx["redis"], proposal_id, {...})` for `pipeline_error`. `publish(redis, proposal_id, payload)` is in `app/infrastructure/queue/events.py`.
- **API process** sets `state="queued"`: `ChatViewModel._dispatch_intent` re_run_phase branch (sub-slice 2) and `POST /chat/{id}/retry` (`backend/app/views/v1/chat.py`). The API process broadcasts via `ws_manager.broadcast(str(pid), payload)` OR `publish(self._request.app.state.arq_pool, ...)` — `ws_manager.broadcast` is the direct in-process path used elsewhere in the viewmodel.
- **Frontend WS hook** `frontend/src/hooks/use-websocket.ts`: an if/else-if chain on `data.type`. Add a `job_status` branch.
- **Store** `frontend/src/stores/chat-store.ts`: Zustand; add a `jobStatus` slice + `setJobStatus` + include it in `reset()`.
- **Chat container** `frontend/src/components/chat/chat-container.tsx`: renders messages inside a `flex-1 overflow-y-auto` div. The sticky widget goes at the TOP of that scroll area (or just above it) so it stays pinned.
- **message-bubble.tsx**: `role === 'system'` renders a centered pill (this is where pipeline error messages land, with `extra_data.kind === 'error'`).
- **API client** `frontend/src/api/proposals.ts`: TanStack `useMutation` patterns; `useSendMessage` posts to `/chat/{id}/send`. Add `useRetryPhase`.
- **Types** `frontend/src/types/proposal.ts`: `WSMessage` union (extend), `PIPELINE_PHASES` array (phase keys are USER-FACING like `research`, NOT job names like `run_research` — the widget must map job-name→label; see Task 3).

---

## File map
**Modify (backend):**
- `backend/app/workers/pipeline.py` — broadcast `job_status` after each `_set_job_status` (Task 1)
- `backend/app/viewmodels/chat_viewmodel.py` — broadcast queued in re_run_phase dispatch (Task 1)
- `backend/app/views/v1/chat.py` — broadcast queued in the retry endpoint (Task 1)

**Modify (frontend):**
- `frontend/src/types/proposal.ts` — `JobStatus` type + extend `WSMessage` (Task 2)
- `frontend/src/stores/chat-store.ts` — `jobStatus` slice (Task 2)
- `frontend/src/hooks/use-websocket.ts` — `job_status` handler (Task 2)
- `frontend/src/api/proposals.ts` — `useRetryPhase` (Task 3)
- `frontend/src/components/chat/chat-container.tsx` — mount `PhaseProgress` (Task 3)

**Create (frontend):**
- `frontend/src/components/chat/phase-progress.tsx` — the sticky widget (Task 3)
- tests alongside existing `__tests__` dirs (Tasks 2, 3)

---

## Task 1 (backend): broadcast `job_status` WS events

**Files:** `backend/app/workers/pipeline.py`, `backend/app/viewmodels/chat_viewmodel.py`, `backend/app/views/v1/chat.py`
**Tests:** `backend/tests/integration/test_pipeline_worker.py`, `backend/tests/integration/test_chat_api.py` (or `test_chat_intent_dispatch.py`)

### Step 1: Write failing tests

- [ ] In `backend/tests/integration/test_pipeline_worker.py`, add a test that runs `_run_phase` (success path) and asserts a `job_status` event with `state="running"` AND one with `state="complete"` were published. Mirror the existing `_run_phase` test's fixture pattern (mock `ctx["redis"]` as AsyncMock, mock the PipelineService phase to succeed). Assert by scanning `redis.publish` await calls and JSON-decoding the envelopes:
```python
async def test_run_phase_broadcasts_job_status_running_then_complete(db, make_proposal_db, monkeypatch):
    import json
    from unittest.mock import AsyncMock
    from app.workers.pipeline import _run_phase
    from app.services.pipeline_service import PipelineService
    monkeypatch.setattr(PipelineService, "run_research", AsyncMock(return_value=None))
    agency, client, proposal = await make_proposal_db()
    redis = AsyncMock()
    await _run_phase({"redis": redis}, "run_research", str(proposal.id))
    # collect job_status payloads from publish envelopes
    states = []
    for call in redis.publish.await_args_list:
        env = json.loads(call.args[1])
        if env["payload"].get("type") == "job_status":
            states.append(env["payload"]["state"])
    assert "running" in states and "complete" in states
```
Confirm the real `publish` signature is `publish(redis, proposal_id, payload)` → it calls `redis.publish(WS_CHANNEL, json.dumps({"proposal_id":..., "payload": payload}))`, so `call.args[1]` is the JSON envelope. (Verify against `events.py` and adjust the decode if the arg position differs.)

- [ ] Add a failed-path test asserting a `job_status` with `state="failed"` and a non-null `error` is published when the phase raises.

Run them — expect failure (no job_status broadcast yet).

### Step 2: Broadcast from the worker

- [ ] In `backend/app/workers/pipeline.py`, make `_set_job_status` also publish the event when a redis client is available. Cleanest: give it an optional `redis` param and publish the same dict it persisted:
```python
async def _set_job_status(session, proposal_id, phase, state, error=None, redis=None) -> None:
    repo = ProposalRepository(session)
    proposal = await repo.get_by_id(proposal_id)
    if proposal is None:
        return
    pipeline = proposal.pipeline_state.copy()
    job_status = {
        "phase": phase, "state": state, "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    pipeline["job_status"] = job_status
    await repo.update(proposal_id, pipeline_state=pipeline)
    await session.commit()
    if redis is not None:
        await publish(redis, proposal_id, {"type": "job_status", **job_status})
```
Then update the three calls in `_run_phase` to pass `ctx["redis"]`:
```python
        await _set_job_status(session, proposal_id, phase, "running", redis=ctx["redis"])
        ...
        await _set_job_status(session, proposal_id, phase, "failed", str(exc), redis=ctx["redis"])
        ...
        await _set_job_status(session, proposal_id, phase, "complete", redis=ctx["redis"])
```
`publish` is already importable in this module? Check — the module imports `from app.infrastructure.queue.events import publish` already (it uses it for pipeline_error). If not, add it.

### Step 3: Broadcast queued from the API process

- [ ] In `chat_viewmodel.py`, the re_run_phase branch of `_dispatch_intent` (sub-slice 2) currently does: `_set_job_queued` → `proposal_repo.update(pipeline_state=...)` → `commit()` → `_enqueue`. After the commit (before or after enqueue is fine), broadcast queued:
```python
            await ws_manager.broadcast(str(proposal_id), {
                "type": "job_status", "phase": job, "state": "queued", "error": None,
            })
```
(`ws_manager` is already imported in this file.)

- [ ] In `backend/app/views/v1/chat.py`, the `retry` endpoint sets job_status queued and re-enqueues. After it persists, broadcast the same queued event. Read the endpoint to see whether it has a redis/ws_manager handle; `ws_manager` can be imported (`from app.core.ws_manager import ws_manager`) and called directly, OR use `publish(request.app.state.arq_pool, proposal_id, {...})`. Match whatever the surrounding code uses for broadcasts. The payload:
```python
{"type": "job_status", "phase": phase, "state": "queued", "error": None}
```

### Step 4: Run tests + full suite + ruff + commit
```
cd backend
uv run pytest tests/integration/test_pipeline_worker.py tests/integration/test_chat_api.py tests/integration/test_chat_intent_dispatch.py -v
uv run pytest -q          # full suite green (prior 506 + new tests)
uv run ruff check app/workers/pipeline.py app/viewmodels/chat_viewmodel.py app/views/v1/chat.py
```
Commit (after branch-safety check):
```
git add backend/app/workers/pipeline.py backend/app/viewmodels/chat_viewmodel.py backend/app/views/v1/chat.py backend/tests/integration/test_pipeline_worker.py
# add test_chat_api.py / test_chat_intent_dispatch.py if you added queued-broadcast tests there
git commit -m "feat(ws): broadcast job_status transitions for the progress widget"
```

**Note:** the existing `_set_job_status` callers without `redis` still work (param is optional, default None → no broadcast). Confirm no other caller breaks (grep `_set_job_status`).

---

## Task 2 (frontend): types + store slice + WS handler

**Files:** `frontend/src/types/proposal.ts`, `frontend/src/stores/chat-store.ts`, `frontend/src/hooks/use-websocket.ts`
**Tests:** follow patterns in `frontend/src/stores/__tests__/` and `frontend/src/hooks/__tests__/` (read an existing one first to match the harness).

### Step 1: Types

- [ ] In `frontend/src/types/proposal.ts`, add:
```ts
export interface JobStatus {
  phase: string
  state: 'queued' | 'running' | 'complete' | 'failed'
  error?: string | null
  updated_at?: string
}
```
- [ ] Extend `WSMessage`: add `'job_status'` to the `type` union and add optional fields `state?: string` and `updated_at?: string` (it already has `phase`, `error`).

### Step 2: Store slice (TDD)

- [ ] Write a failing store test (in `frontend/src/stores/__tests__/`, matching the existing chat-store test style) asserting `setJobStatus` sets the slice and `reset()` clears it to `null`.
- [ ] In `chat-store.ts`: add `jobStatus: JobStatus | null` to the state interface + initial value `null`; add `setJobStatus: (s: JobStatus | null) => void`; implement `setJobStatus: (s) => set({ jobStatus: s })`; add `jobStatus: null` to the `reset()` payload. Import the `JobStatus` type.

### Step 3: WS handler (TDD)

- [ ] In the WS hook test (or a focused unit test of the message handler), assert a `{type:'job_status',...}` message calls `setJobStatus`. If the existing hook tests drive `ws.onmessage` via a mock socket, follow that; otherwise add a minimal test.
- [ ] In `use-websocket.ts`: pull `setJobStatus` from the store (`const setJobStatus = useChatStore((s) => s.setJobStatus)`), add it to the `useEffect` dependency array, and add a handler branch:
```ts
          } else if (data.type === 'job_status' && data.phase && data.state) {
            setJobStatus({
              phase: data.phase,
              state: data.state as JobStatus['state'],
              error: data.error ?? null,
              updated_at: data.updated_at,
            })
```
Import `JobStatus` type. Place the branch before the `pipeline_error` branch.

### Step 4: Run frontend tests + commit
```
cd frontend
pnpm test --run     # all green (prior 275 + new)
pnpm exec tsc -b --noEmit   # typecheck clean (or the project's typecheck script — check package.json)
pnpm exec eslint src/stores/chat-store.ts src/hooks/use-websocket.ts src/types/proposal.ts
```
Commit (after branch-safety check):
```
git add frontend/src/types/proposal.ts frontend/src/stores/chat-store.ts frontend/src/hooks/use-websocket.ts \
        frontend/src/stores/__tests__/<the test files you touched>
git commit -m "feat(ws): frontend job_status store slice + websocket handler"
```

---

## Task 3 (frontend): PhaseProgress sticky widget + Retry

**Files:** create `frontend/src/components/chat/phase-progress.tsx`; modify `frontend/src/api/proposals.ts`, `frontend/src/components/chat/chat-container.tsx`
**Tests:** `frontend/src/components/chat/__tests__/phase-progress.test.tsx` (match the existing component-test harness — read one first)

### Step 1: Retry mutation

- [ ] In `frontend/src/api/proposals.ts`, add (matching the existing mutation style):
```ts
export function useRetryPhase(proposalId: string) {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/chat/${proposalId}/retry`)
      return data
    },
  })
}
```

### Step 2: Write the failing component test

- [ ] Create `frontend/src/components/chat/__tests__/phase-progress.test.tsx`. Read an existing component test (e.g. the cost-model or approval-gate test) to copy the render harness (React Testing Library + any QueryClient/store providers). Tests to write:
  - renders nothing when `jobStatus` is null;
  - shows the humanized phase label + a "Running" indicator when state is `running`;
  - shows a "Done"/complete indicator when `complete`;
  - shows the error text + a **Retry** button when `failed`;
  - clicking Retry calls the retry endpoint (mock `useRetryPhase`/the api).
Drive `jobStatus` by setting it on the store before render (the store is a singleton zustand hook — set via `useChatStore.setState({ jobStatus: {...} })` or the store's `setJobStatus`).

### Step 3: Implement `PhaseProgress`

- [ ] Create `frontend/src/components/chat/phase-progress.tsx`:
  - Reads `const jobStatus = useChatStore((s) => s.jobStatus)`. Returns `null` if `jobStatus == null`.
  - **Phase label:** map the job-name `phase` to a friendly label. Job names → labels:
    `analyze_brief→"Brief"`, `run_research→"Research"`, `run_benchmarks→"Benchmarks"`, `build_cost_model→"Cost Model"`, `generate_sections→"Sections"`. Fall back to a humanized version (`phase.replace(/_/g,' ')`) for anything unknown. (Do NOT reuse `PIPELINE_PHASES` directly — its keys are user-facing phases, not job names.)
  - **State rendering:** `queued` → muted "Queued" + dot; `running` → spinner + "Running" + a live elapsed timer; `complete` → green check + "Complete"; `failed` → red icon + "Failed" + `error` text + a **Retry** button (calls `useRetryPhase(proposalId).mutate()`, disabled while pending).
  - **Elapsed timer (running only):** compute from `jobStatus.updated_at`. Use a `useEffect` + `setInterval(1000)` that ticks a `now` state; render `Math.max(0, Math.floor((now - Date.parse(updated_at))/1000))` as `m:ss`. Clear the interval when state !== 'running' or on unmount.
  - **Styling:** a compact horizontal bar — `sticky top-0 z-10` with a solid background (`bg-white/95 backdrop-blur border-b border-stone-200 px-6 py-2`) so it pins to the top of the scroll area and content scrolls under it. Match the existing stone/Tailwind palette (see PipelineSidebar/ProgressTracker for the visual language: stone grays, green-500 complete, red-500 error, spinner `border-t-stone-900`).
  - Takes `proposalId: string` as a prop (needed for the retry mutation).
  - CSS stays in Tailwind classes (the project uses Tailwind utility classes inline — that's the established pattern here, not separate CSS files).

### Step 4: Mount it in the chat container

- [ ] In `chat-container.tsx`, render `<PhaseProgress proposalId={proposalId} />` as the FIRST child inside the `flex-1 overflow-y-auto` scroll div (so `sticky top-0` pins it to the top of the scrolling message area). Import it. Do not disturb the existing message map / ProgressTracker / TypingIndicator.

### Step 5: Run tests + typecheck + lint + commit
```
cd frontend
pnpm test --run
pnpm exec tsc -b --noEmit       # or the project typecheck script
pnpm exec eslint src/components/chat/phase-progress.tsx src/components/chat/chat-container.tsx src/api/proposals.ts
```
Commit (after branch-safety check):
```
git add frontend/src/components/chat/phase-progress.tsx frontend/src/components/chat/chat-container.tsx \
        frontend/src/api/proposals.ts frontend/src/components/chat/__tests__/phase-progress.test.tsx
git commit -m "feat(chat): sticky PhaseProgress widget with retry on failed phases"
```

---

## Sub-slice 3 done
- [ ] `cd backend && uv run pytest -q` green; `cd frontend && pnpm test --run` green; frontend typecheck + eslint clean.
- [ ] Visual verification (controller will handle): run the dev server + drive the chat, observe the PhaseProgress widget transition queued→running→complete and the failed+Retry state via Playwright/devtools. A UI change is not done until visually verified.

---

## Self-review checklist (pre-execution)
- [x] **Spec coverage:** P9 (PhaseProgress: phase, state, elapsed, error — sticky top-of-chat) and P10 (Retry on failed) both covered. Backed by the user-chosen Option A (real `job_status` WS broadcast).
- [x] **Contract consistency:** the `job_status` event shape (`type, phase, state, error, updated_at`) is identical across the worker broadcast (Task 1), the API queued broadcast (Task 1), the `WSMessage` type + WS handler (Task 2), and the `JobStatus` store type + widget (Tasks 2-3). `phase` is the ARQ job name everywhere; the widget is the only place that maps job-name→label (flagged explicitly so no one reuses PIPELINE_PHASES wrongly).
- [x] **No double abstraction:** retry reuses the existing `POST /chat/{id}/retry`; no new retry endpoint. The widget reuses existing Tailwind/stone visual language.
- [x] **Backward-compat:** `_set_job_status`'s new `redis` param is optional (default None) so any other caller is unaffected — flagged to grep callers.
- [x] **Placeholder scan:** no TBDs; the only "read first" notes are for matching existing frontend test harnesses (unavoidable — the harness shape must be copied, not guessed) and confirming the retry endpoint's broadcast handle.
