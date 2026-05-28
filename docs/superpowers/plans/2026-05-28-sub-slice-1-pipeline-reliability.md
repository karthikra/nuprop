# Sub-Slice 1: Pipeline Reliability Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three operational footguns that bit prod during today's S10 smoke testing: (1) Fly worker stays stopped after every secret change, (2) ARQ result-cache silently swallows phase-chain retries, (3) hosted web_search responses store an empty citations list.

**Architecture:** Three independent fixes shipped as one slice (commits land separately). P1 is a workflow-yaml change. P2 extracts a small shared helper from `chat_viewmodel._enqueue_phase_job` and routes the four other enqueue sites through it. P4 is a probe-then-fix because the prod response shape isn't known yet.

**Tech Stack:** GitHub Actions, Fly.io / flyctl, ARQ 0.26+, Anthropic Python SDK (direct API, not Bedrock), pytest, pytest-asyncio.

**Source spec:** `docs/superpowers/specs/2026-05-27-post-s10-stability-and-chat-intent.md` Group B items P1, P2, P4.

---

## File map

**Modify:**
- `.github/workflows/deploy.yml` — append worker auto-restart step (Task 1)
- `backend/app/workers/pipeline.py:78` — switch chain enqueue to shared helper (Task 2)
- `backend/app/viewmodels/chat_viewmodel.py:40-79` — `_enqueue_phase_job` delegates to shared helper (Task 2)
- `backend/app/views/v1/proposals.py:189, 214, 279` — three retry-style enqueues route through helper (Task 2)
- `backend/app/services/research_streaming.py` (line range determined by probe) — citation extraction fix (Task 3)

**Create:**
- `backend/app/infrastructure/queue/enqueue.py` — new shared helper module (Task 2)
- `backend/tests/integration/test_pipeline_worker.py` — add new tests; file exists
- `backend/tests/integration/test_proposals_retry_trap.py` — new file, covers rate-card-gaps + rate-card-import (Task 2)
- `backend/scripts/probe_web_search_citations.py` — one-shot probe script (Task 3)
- `backend/tests/integration/test_research_streaming.py` — add new test mirroring captured shape (Task 3)

**Delete after Task 3:**
- `backend/scripts/probe_web_search_citations.py` (per "clean up helper files at end of task" rule)

---

## Task 1: P1 — Auto-restart Fly worker process group after deploy

**Why:** `min_machines_running = 1` in `fly.toml` is scoped to `processes = ['app']`. The worker has no equivalent guarantee and no HTTP traffic to wake it. Every `fly secrets set` (and every redeploy) leaves it in `stopped` state — chat looks alive but jobs queue with no consumer. HANDOFF § 5b documents the manual jq one-liner; this task wires it into CI.

**Files:**
- Modify: `.github/workflows/deploy.yml` (full current file shown below — only the deploy job changes)

**Current state:**
```yaml
name: Deploy to Fly.io

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: superfly/flyctl-actions/setup-flyctl@master

      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

- [ ] **Step 1: Edit `.github/workflows/deploy.yml` — add post-deploy worker-restart step**

Append a single step after `flyctl deploy`. Must be in the same job so `FLY_API_TOKEN` from the deploy step's env is in scope.

```yaml
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

      - name: Ensure worker process group is running
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: |
          flyctl machine list -a nuprop --json \
            | jq -r '.[] | select(.config.metadata.fly_process_group == "worker" and .state == "stopped") | .id' \
            | xargs -r -I{} flyctl machine start {} -a nuprop
```

- [ ] **Step 2: Lint the YAML locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
Expected: exits 0, no output. (We don't have actionlint in the toolchain; YAML parse is the cheapest sanity check.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci(deploy): auto-restart Fly worker process group after deploy"
```

**Note on verification:** We can't fully verify this step until the slice merges to `main` and the workflow runs. The slice's "Finish the development branch" task (super-skill `finishing-a-development-branch`) covers the manual smoke-test plan: trigger the workflow via `gh workflow run deploy.yml`, then `fly status -a nuprop` to confirm the worker is `started`. Document this in HANDOFF § 5b cleanup.

---

## Task 2: P2 — Extract retry-trap fix into shared helper, route 5 enqueue sites through it

**Why:** Today's commit `74568b3` fixed the ARQ result-cache retry trap, but only inside `ChatViewModel._enqueue_phase_job`. The bug ("ARQ's 24h result-cache silently swallows re-enqueues of the same `_job_id`") exists in 4 OTHER enqueue sites that don't use the helper:

| File | Line | Site |
|---|---|---|
| `backend/app/workers/pipeline.py` | 78 | `_run_phase` chain (run_research → run_benchmarks → build_cost_model) |
| `backend/app/views/v1/proposals.py` | 189 | rate-card-gaps submit |
| `backend/app/views/v1/proposals.py` | 214 | rate-card-gaps skip |
| `backend/app/views/v1/proposals.py` | 279 | rate-card-import |

(Connector's `enqueue_context` uses a timestamp-suffixed `_job_id` so it's unique-per-call → no trap. Skip.)

Cleanest fix: extract a small free function the viewmodel, worker, and views can all call. This also makes the test surface tighter — one function to unit-test, four call-site assertions to integration-test.

**Files:**
- Create: `backend/app/infrastructure/queue/enqueue.py` — new helper
- Modify: `backend/app/viewmodels/chat_viewmodel.py:40-79` — delegate
- Modify: `backend/app/workers/pipeline.py:78` — call helper
- Modify: `backend/app/views/v1/proposals.py:189, 214, 279` — call helper
- Test: `backend/tests/integration/test_pipeline_worker.py` — add chain retry-trap regression
- Test: `backend/tests/integration/test_proposals_retry_trap.py` — new, covers rate-card endpoints

### Step 1: Write the failing test for the new helper module (unit-level)

- [ ] Create `backend/tests/unit/test_enqueue_helper.py`:

```python
"""Unit tests for the shared `enqueue_phase_job` helper.

The helper exists because ARQ uses ``_job_id`` as a 24h result-cache key.
A failed prior run leaves a poisoned key, and subsequent re-enqueues
silently no-op until the TTL expires. The fix is to DEL the result key
before every enqueue. This was previously inlined in chat_viewmodel; this
test pins the contract for the extracted helper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.queue.enqueue import enqueue_phase_job


@pytest.mark.asyncio
async def test_deletes_result_key_then_enqueues():
    pool = AsyncMock()
    await enqueue_phase_job(
        pool, job_name="run_research", proposal_id="abc-123",
    )
    pool.delete.assert_awaited_once_with("arq:result:abc-123:run_research")
    pool.enqueue_job.assert_awaited_once_with(
        "run_research", "abc-123", _job_id="abc-123:run_research",
    )


@pytest.mark.asyncio
async def test_delete_failure_does_not_block_enqueue():
    """A transient Redis hiccup on DEL must not poison the actual enqueue.
    Mirrors the inline behaviour from chat_viewmodel._enqueue_phase_job."""
    pool = AsyncMock()
    pool.delete.side_effect = ConnectionError("redis transient")
    await enqueue_phase_job(
        pool, job_name="run_research", proposal_id="abc-123",
    )
    pool.enqueue_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_idempotency_key_makes_job_id_unique():
    """For per-turn enqueues (analyze_brief on each chat send) the caller
    can pass an idempotency_key — the resulting _job_id is unique so the
    result-key DEL is a harmless no-op."""
    pool = AsyncMock()
    await enqueue_phase_job(
        pool, job_name="analyze_brief", proposal_id="abc-123",
        idempotency_key="turn-7",
    )
    pool.delete.assert_awaited_once_with("arq:result:abc-123:analyze_brief:turn-7")
    pool.enqueue_job.assert_awaited_once_with(
        "analyze_brief", "abc-123", _job_id="abc-123:analyze_brief:turn-7",
    )
```

### Step 2: Run the test to verify it fails

Run: `cd backend && uv run pytest tests/unit/test_enqueue_helper.py -v`
Expected: 3 errors with `ModuleNotFoundError: No module named 'app.infrastructure.queue.enqueue'`.

### Step 3: Create the helper module

- [ ] Create `backend/app/infrastructure/queue/enqueue.py`:

```python
"""Shared ARQ enqueue helper that defangs the result-cache retry trap.

ARQ uses ``_job_id`` for two flavours of deduplication:

* **In-flight dedup** — if a job with the same ``_job_id`` is currently
  queued or being processed, ARQ silently drops the duplicate. This is
  the property we want: protects against double-click on Approve, double
  webhook delivery, etc.
* **Result-cache dedup** — once a job finishes (success OR failure), ARQ
  stores its result under ``arq:result:<job_id>`` for 24h. While that
  key exists, every subsequent ``enqueue_job`` for the same ``_job_id``
  silently no-ops. **This breaks the retry-after-failure flow** — a
  failed gate-approval leaves a poisoned result key, and every later
  "retry" silently no-ops for the TTL window.

The fix: explicitly ``DEL`` the result key before enqueueing. In-flight
dedup still works (queue/in-progress keys are not touched).

Callers that need a fresh run per invocation (e.g. ``analyze_brief`` per
chat turn) pass an ``idempotency_key`` so the resulting ``_job_id`` is
unique; the DEL is a no-op for those since the key never existed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def enqueue_phase_job(
    pool: Any,
    *,
    job_name: str,
    proposal_id: str,
    idempotency_key: str | None = None,
) -> None:
    """DEL the result-cache key, then enqueue the job.

    ``pool`` is an ARQ pool (``ArqRedis``) — duck-typed here so the helper
    is trivially mockable in tests.
    """
    suffix = f":{idempotency_key}" if idempotency_key else ""
    job_id = f"{proposal_id}:{job_name}{suffix}"
    try:
        await pool.delete(f"arq:result:{job_id}")
    except Exception:  # noqa: BLE001 — DEL must not poison the enqueue
        logger.debug(
            "redis DEL failed before enqueue (job_id=%s); continuing", job_id,
        )
    await pool.enqueue_job(job_name, str(proposal_id), _job_id=job_id)
```

### Step 4: Run the test to verify it passes

Run: `cd backend && uv run pytest tests/unit/test_enqueue_helper.py -v`
Expected: 3 passed.

### Step 5: Refactor `chat_viewmodel._enqueue_phase_job` to delegate

The viewmodel currently inlines the DEL+enqueue. Switch it to call the helper. Public signature on `_enqueue` (private to the viewmodel) stays the same so callers don't change.

- [ ] Edit `backend/app/viewmodels/chat_viewmodel.py` — replace the body of `_enqueue` (currently lines ~40-79):

```python
    async def _enqueue(
        self,
        job_name: str,
        proposal_id,
        idempotency_key: str | None = None,
    ) -> None:
        """Thin wrapper around the shared :func:`enqueue_phase_job` helper.

        See ``app.infrastructure.queue.enqueue`` for the full rationale on why
        the result-key DEL is needed before every enqueue.
        """
        from app.infrastructure.queue.enqueue import enqueue_phase_job
        await enqueue_phase_job(
            self._request.app.state.arq_pool,
            job_name=job_name,
            proposal_id=str(proposal_id),
            idempotency_key=idempotency_key,
        )
```

Import at module-top vs inline: keep inline to avoid adding a new top-of-file import for a tightly-scoped one-line use. (The existing file uses lazy imports for other infrastructure modules per its style.)

### Step 6: Refactor `workers/pipeline.py:78` chain enqueue

- [ ] Edit `backend/app/workers/pipeline.py` — replace the `next_phase` block at the end of `_run_phase`:

```python
    next_phase = _NEXT_PHASE.get(phase)
    if next_phase:
        from app.infrastructure.queue.enqueue import enqueue_phase_job
        await enqueue_phase_job(
            ctx["redis"],
            job_name=next_phase,
            proposal_id=str(proposal_id),
        )
```

### Step 7: Refactor the three `views/v1/proposals.py` enqueue sites

Each currently calls `pool.enqueue_job("run_research", str(proposal_id), _job_id=f"{proposal_id}:run_research")` directly. Switch all three.

- [ ] Edit `backend/app/views/v1/proposals.py` around line 189 (rate-card-gaps submit):

```python
    from app.infrastructure.queue.enqueue import enqueue_phase_job
    await enqueue_phase_job(
        request.app.state.arq_pool,
        job_name="run_research",
        proposal_id=str(proposal_id),
    )
    return {"ok": True}
```

- [ ] Same change around line 214 (rate-card-gaps skip):

```python
    from app.infrastructure.queue.enqueue import enqueue_phase_job
    await enqueue_phase_job(
        request.app.state.arq_pool,
        job_name="run_research",
        proposal_id=str(proposal_id),
    )
    return Response(status_code=204)
```

- [ ] Same change around line 279 (rate-card-import):

```python
    from app.infrastructure.queue.enqueue import enqueue_phase_job
    await enqueue_phase_job(
        request.app.state.arq_pool,
        job_name="run_research",
        proposal_id=str(proposal_id),
    )
    return {"ok": True}
```

The local `from ... import enqueue_phase_job` is duplicated in three places. Acceptable: each site is a small handler, the symbol is in-file at the call site, and the alternative (one top-of-file import) bloats an already 300+ line module. Keep duplicated lazy imports.

### Step 8: Add chain retry-trap regression test in `test_pipeline_worker.py`

The existing test at line 87 (`ctx["redis"].enqueue_job.assert_awaited()`) passes today because the bug is "silent no-op" — the enqueue is called, ARQ just ignores it. The new test pins that the worker now DELs the chain's result key first.

- [ ] Append to `backend/tests/integration/test_pipeline_worker.py`:

```python
async def test_chain_enqueue_clears_stale_result_key_before_enqueueing_next_phase(
    db, make_proposal_db, mock_pipeline_service_phase,
):
    """Regression for the worker chain (run_research -> run_benchmarks ->
    build_cost_model). Mirrors the chat_viewmodel fix in commit 74568b3:
    a failed prior run on the SAME _job_id leaves a poisoned arq:result
    key (24h TTL). The chain MUST DEL it before enqueueing the next phase
    so re-runs aren't silently swallowed."""
    from app.workers.pipeline import _run_phase
    proposal = await make_proposal_db()
    redis = AsyncMock()

    with mock_pipeline_service_phase("run_research"):
        await _run_phase({"redis": redis}, "run_research", str(proposal.id))

    # DEL must precede enqueue and target the chained phase's result key.
    redis.delete.assert_awaited_once_with(
        f"arq:result:{proposal.id}:run_benchmarks"
    )
    redis.enqueue_job.assert_awaited_once()
    assert redis.enqueue_job.await_args.args[0] == "run_benchmarks"
```

Note: this test assumes a `mock_pipeline_service_phase` fixture exists. Check `backend/tests/conftest.py` and the existing `test_pipeline_worker.py` for what fixture name/shape is actually used (the file already has `_run_phase` tests at lines 87+ — copy that pattern verbatim if the fixture name differs). If no fixture exists, monkeypatch `app.services.pipeline_service.PipelineService.run_research` to an `AsyncMock()` inline.

### Step 9: Add rate-card-endpoint regression test

- [ ] Create `backend/tests/integration/test_proposals_retry_trap.py`:

```python
"""Regression: the three rate-card endpoints in views/v1/proposals.py
that enqueue ``run_research`` must DEL the stale result key first.

Without this, a failed initial research run leaves a poisoned
arq:result:<pid>:run_research key (24h TTL) — every subsequent rate-card
gap-submit / skip / import silently no-ops, breaking the recover flow.
"""

from __future__ import annotations

import pytest


API = "/api/v1"


@pytest.mark.parametrize(
    "endpoint,method,body",
    [
        ("rate-card-gaps/submit", "post", {"hourly_rates": [], "offerings": []}),
        ("rate-card-gaps/skip", "post", None),
        ("rate-card-import", "post", {"raw_text": "Logo: 50000\n"}),
    ],
)
async def test_rate_card_endpoints_clear_stale_result_key_before_enqueue(
    client, registered, arq_pool, make_proposal_api,
    endpoint, method, body,
):
    p = await make_proposal_api(client, registered.headers)
    url = f"{API}/proposals/{p['id']}/{endpoint}"
    if body is None:
        resp = await getattr(client, method)(url, headers=registered.headers)
    else:
        resp = await getattr(client, method)(
            url, headers=registered.headers, json=body,
        )
    assert resp.status_code in (200, 204)

    arq_pool.delete.assert_awaited()
    assert arq_pool.delete.await_args.args[0] == f"arq:result:{p['id']}:run_research"
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"
```

Note: `rate-card-import` may need a more complete body to pass validation (real schema TBD). Check `backend/app/views/v1/proposals.py:271+` for the actual endpoint signature and adjust the request body to satisfy validation. If the endpoint depends on `proposal.rate_card_gaps` being populated first, seed it in the test (mirror the seeding pattern from `tests/integration/test_rate_card_gaps_endpoints.py`).

### Step 10: Run all touched tests

Run: `cd backend && uv run pytest tests/unit/test_enqueue_helper.py tests/integration/test_pipeline_worker.py tests/integration/test_proposals_retry_trap.py tests/integration/test_chat_api.py -v`
Expected: all green. The existing `test_approve_gate_clears_stale_arq_result_before_enqueue` should still pass since the viewmodel's contract is unchanged.

### Step 11: Run the full backend suite to catch refactor blast-radius

Run: `cd backend && uv run pytest -q`
Expected: 467 + 3 (new helper unit tests) + 1 (new chain trap test) + 3 (new parametrized rate-card tests) = **474 passed**. If the count is off, investigate.

### Step 12: Commit

```bash
git add backend/app/infrastructure/queue/enqueue.py \
        backend/app/viewmodels/chat_viewmodel.py \
        backend/app/workers/pipeline.py \
        backend/app/views/v1/proposals.py \
        backend/tests/unit/test_enqueue_helper.py \
        backend/tests/integration/test_pipeline_worker.py \
        backend/tests/integration/test_proposals_retry_trap.py
git commit -m "fix(arq): extract retry-trap fix into shared helper, apply to all enqueue sites"
```

---

## Task 3: P4 — Diagnose + fix hosted-tool citation extraction

**Why:** `process_stream` is silently storing `extra_data.citations == []` for `benchmarks_findings` rows even when the markdown body has source mentions. The existing unit tests for `process_stream` pass — meaning the documented contract works against synthetic fixtures but doesn't match what the live SDK is returning. Either the SDK response shape changed since the tests were written, or citations come through a content-block type the code doesn't read, or the substring-match span computation is filtering out every citation (the existing `test_process_stream_skips_citations_whose_cited_text_is_not_in_body` test documents this as a known v1 limitation — a "Future v2: fuzzy match" comment lives in the source).

**This task is investigation-first.** TDD only works once we have evidence of the actual shape. The first step captures real data; the failing test is written against captured data, not guessed.

**Files:**
- Create: `backend/scripts/probe_web_search_citations.py` — one-shot probe
- Modify: `backend/app/services/research_streaming.py` — fix (specifics depend on capture)
- Modify: `backend/tests/integration/test_research_streaming.py` — add captured-shape test

### Step 1: Write the probe script

- [ ] Create `backend/scripts/probe_web_search_citations.py`:

```python
"""One-shot probe: dump the raw stream events from a live hosted web_search
call so we can see exactly what shape Anthropic returns and confirm why
``process_stream`` is producing ``citations == []`` in prod.

Run locally:
    cd backend
    ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/probe_web_search_citations.py

Writes to: ./probe_capture.json (gitignored — clean up at end of task).

The script does NOT call process_stream. It iterates the raw stream and
serializes every event's structure verbatim so we can answer:

  1. Are text blocks coming back with a non-empty `citations` attr?
  2. If yes, do their `cited_text` strings appear as substrings of the
     surrounding `block.text`?
  3. If no, where do the citations live? (web_search_tool_result.content?
     A different block type entirely?)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from anthropic import AsyncAnthropic


def _to_serializable(obj: Any) -> Any:
    """Best-effort flattener for SDK objects (Pydantic models, namedtuples)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return {k: _to_serializable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)


async def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY must be set")

    client = AsyncAnthropic(api_key=api_key)
    captured: list[dict[str, Any]] = []

    async with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="You are a research assistant. Cite every numeric claim.",
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": (
            "What was Apple's Q4 2025 revenue? Cite your source."
        )}],
    ) as stream:
        async for event in stream:
            captured.append({
                "type": getattr(event, "type", None),
                "raw": _to_serializable(event),
            })

    with open("probe_capture.json", "w") as f:
        json.dump(captured, f, indent=2, default=str)

    print(f"Captured {len(captured)} events to probe_capture.json")
    text_blocks = [
        e for e in captured
        if e["type"] == "content_block_stop"
        and isinstance(e.get("raw"), dict)
        and (e["raw"].get("content_block") or {}).get("type") == "text"
    ]
    print(f"Text content_block_stop events: {len(text_blocks)}")
    for tb in text_blocks:
        cb = tb["raw"]["content_block"]
        cits = cb.get("citations") or []
        print(f"  text len={len(cb.get('text') or '')}, citations={len(cits)}")
        for c in cits:
            cited = c.get("cited_text", "")
            text = cb.get("text") or ""
            in_text = cited in text
            print(f"    cited_text len={len(cited)}, in_block_text={in_text}")
            if not in_text:
                print(f"      cited: {cited[:80]!r}")
                print(f"      block: {text[:80]!r}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 2: Run the probe locally

Run:
```bash
cd backend
ANTHROPIC_API_KEY=$(fly secrets list -a nuprop --json | jq -r '.[] | select(.Name=="ANTHROPIC_API_KEY")') \
  # Above line WON'T work — Fly doesn't expose secret values.
  # Instead: grab the key from https://console.anthropic.com/account/keys
  # (the same one set in Fly secrets) and export it locally.
ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/probe_web_search_citations.py
```

Expected: writes `probe_capture.json`. The console summary lists how many `text` blocks came back, how many citations each carries, and — critically — whether each `cited_text` appears as a verbatim substring of its block's text.

**Decision branch:**

- **Branch A — `text` blocks have citations, all `in_block_text == True`:** The bug is somewhere else (maybe storage; check `pipeline_service.run_research` writes citations through). Stop and re-investigate; do not proceed to Step 3 with the wrong hypothesis.
- **Branch B — `text` blocks have citations but `in_block_text == False`:** Confirmed: the substring-match span computation is filtering everything. Fix at Step 3 below.
- **Branch C — `text` blocks have empty/missing citations:** Citations live elsewhere. Inspect `probe_capture.json` manually for any block carrying `cited_text`. Likely candidates: `web_search_tool_result.content[*]` entries themselves, or a new `citation` content-block type. Fix at Step 3 must extend the extractor.

### Step 3: Write the failing test using captured data

This step's exact code depends on which branch in Step 2 was taken. Below is the test for **Branch B** (most likely given the v1 comment in `research_streaming.py`).

- [ ] Append to `backend/tests/integration/test_research_streaming.py`:

```python
async def test_process_stream_includes_paraphrased_citations_with_null_span():
    """When Claude paraphrases the cited_text slightly so it isn't a verbatim
    substring of the surrounding block_text, the citation must still be
    captured (with span=None) — NOT dropped silently.

    Production regression: today's smoke run produced an empty `citations`
    list for every benchmarks_findings row because every paraphrase was
    being filtered by the substring check. The user-visible body had source
    mentions but the citations array was empty — frontend rendered no
    source pills.
    """
    events, on_event = await _make_collector()
    body_text = "Apple posted record Q4 revenue."
    # cited_text differs from any substring of body_text (paraphrase).
    citation = _citation(
        "https://apple.com/q4", "Apple Q4",
        "Apple reported a record fourth-quarter revenue figure",
    )
    stream = _AsyncIter([
        _delta(body_text),
        _stop(_text_block(body_text, citations=[citation])),
    ])
    _, citations, spans = await process_stream(stream, on_event=on_event)
    # Citation MUST be present (was previously dropped).
    assert len(citations) == 1
    assert citations[0]["url"] == "https://apple.com/q4"
    # Span MAY be missing (frontend can render the pill without a body anchor).
    assert spans == [] or (spans[0].get("start") is None and spans[0].get("end") is None)
```

The pre-existing test `test_process_stream_skips_citations_whose_cited_text_is_not_in_body` (line ~269) encodes the OLD "drop on miss" behaviour. **Delete that test** since the contract is changing — or update it to assert the new behaviour. Don't leave a contradicting pair.

### Step 4: Run the new test to verify it fails

Run: `cd backend && uv run pytest tests/integration/test_research_streaming.py::test_process_stream_includes_paraphrased_citations_with_null_span -v`
Expected: FAIL with `assert len(citations) == 1` finding 0 citations.

### Step 5: Implement the fix in `research_streaming.py`

For **Branch B** (most likely): in `process_stream`, change the citation-extraction loop in the `block_type == "text"` branch (around line 191) so a substring-match miss STILL records the citation, just without a span:

- [ ] Edit `backend/app/services/research_streaming.py`. Replace the existing citation loop in the `block_type == "text"` block:

```python
            elif block_type == "text":
                block_text = getattr(block, "text", "") or ""
                text_offset = sum(len(p) for p in body_parts) - len(block_text)
                cursor = 0
                for c in (getattr(block, "citations", None) or []):
                    cit = _ensure_citation(citations, c)
                    cited = getattr(c, "cited_text", "") or ""
                    if not cited:
                        # Citation with no cited_text — still record the source,
                        # just can't anchor it in the body.
                        continue
                    idx = block_text.find(cited, cursor)
                    if idx < 0:
                        # cited_text isn't a verbatim substring — Claude
                        # paraphrased. Keep the citation (source attribution
                        # is the primary value); span anchoring is optional.
                        continue
                    start = text_offset + idx
                    end = start + len(cited)
                    cursor = idx + len(cited)
                    spans.append(
                        {"start": start, "end": end, "citation_ids": [cit["id"]]}
                    )
```

Key change: `_ensure_citation(citations, c)` moves to the TOP of the loop body, so the citation lands in the output list regardless of whether the span anchoring succeeds. Previously it only ran after the substring check passed.

For **Branch C** the fix extends `process_stream` to handle whichever block type carries the citations — write the corresponding loop based on the probe data, not from this template.

### Step 6: Run the failing test to verify it passes

Run: `cd backend && uv run pytest tests/integration/test_research_streaming.py -v`
Expected: all `test_process_stream_*` tests pass (including the new one) and the deleted/updated `test_process_stream_skips_citations_whose_cited_text_is_not_in_body` matches its new behaviour.

### Step 7: Run the full suite

Run: `cd backend && uv run pytest -q`
Expected: 474 + 1 new (or 474 if the deleted-old / added-new netted out) — all green.

### Step 8: Clean up probe artifacts

- [ ] Delete `backend/scripts/probe_web_search_citations.py`
- [ ] Delete `backend/probe_capture.json` if it was committed/staged

```bash
rm backend/scripts/probe_web_search_citations.py
rm -f backend/probe_capture.json
git status  # confirm clean
```

### Step 9: Commit

```bash
git add backend/app/services/research_streaming.py \
        backend/tests/integration/test_research_streaming.py
git commit -m "fix(research): keep citations even when cited_text doesn't substring-match body"
```

If the probe took Branch C, the commit message changes to describe the actual block-type fix.

---

## Sub-slice 1 done — push the branch

After all three tasks land:

- [ ] Verify the worktree is in a clean state and on the right branch

Run:
```bash
git status            # expect clean
git branch --show-current  # expect: worktree-post-s10-stability-and-chat-intent
git log --oneline -4  # expect: 3 new commits + the parent
```

- [ ] Final smoke: full test suite once more

Run: `cd backend && uv run pytest -q`
Expected: all green.

- [ ] Hand off to the `superpowers:finishing-a-development-branch` skill for merge/push.

---

## Self-review checklist (pre-execution)

- [x] **Spec coverage:** P1, P2, P4 all have tasks. P3/P5/P6/P7 explicitly deferred to sub-slice 4.
- [x] **Placeholder scan:** No "TBD", no "fill in", no generic "add error handling". The one conditional area (Task 3 Branch A/B/C) is explicitly named because the probe is required to choose the fix.
- [x] **Type consistency:** `enqueue_phase_job(pool, *, job_name, proposal_id, idempotency_key)` signature is identical across the helper, the unit test, the viewmodel delegate, the worker chain, and all three view sites.
- [x] **One escape hatch flagged:** Step 6 of Task 3 may need to delete the existing `test_process_stream_skips_citations_whose_cited_text_is_not_in_body` test because the contract is changing. Called out inline in Step 3.
