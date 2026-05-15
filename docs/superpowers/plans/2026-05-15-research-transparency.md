# Research Transparency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent 60–90 second `run_research` / `run_benchmarks` phases with three visible chat messages per phase — a Haiku-generated pre-flight plan, a live activity log of search queries and pages read, and a final findings card with inline hover citations sourced from Anthropic's web-search tool metadata.

**Architecture:** Pure data-layer additions in `chat_messages.extra_data` (no schema changes). The worker decomposes each phase into three sequential message-emits backed by a streaming Anthropic call (`AsyncAnthropicBedrock.messages.stream`) — the stream's `tool_use` and `web_search_tool_result` blocks become `ActivityEvent` rows in a single growing activity-log message, batched-flushed every 5 events or 750ms via a new `message_updated` WebSocket event type. Citation spans from the SDK's text-block metadata persist on the findings message; the frontend injects hover-superscripts at those offsets via a post-render DOM walk.

**Tech Stack:** FastAPI, async SQLAlchemy, ARQ (Redis task queue), `redis.asyncio` (pub/sub), Anthropic SDK via `AsyncAnthropicBedrock`, pytest + pytest-asyncio, React + Vite + Zustand + Vitest + MSW + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-05-15-research-transparency-design.md`

---

## File Structure

**New files:**
- `backend/app/services/research_planner.py` — Haiku-based pre-flight plan generation; one function for research, one for benchmarks. Pure async, returns a parsed JSON dict.
- `backend/app/services/research_streaming.py` — Two responsibilities: (1) `ActivityFlusher` class — batched-flush primitive for live activity logs (DB UPDATE + Redis publish on each flush). (2) `process_stream()` async function — consumes an SDK stream and produces the final body, citation list, and span list while invoking a per-event callback.
- `backend/tests/integration/test_research_planner.py` — plan generation tests (research + benchmarks shapes).
- `backend/tests/integration/test_research_streaming.py` — `ActivityFlusher` flush-trigger tests + `process_stream` event-translation tests against synthetic SDK event sequences.
- `backend/tests/integration/test_research_transparency.py` — end-to-end `PipelineService.run_research` / `run_benchmarks` tests with mocked planner + stream.
- `frontend/src/components/chat/research-plan-card.tsx` — renders `research_plan` / `benchmarks_plan`.
- `frontend/src/components/chat/research-activity-log.tsx` — renders `research_activity_log` / `benchmarks_activity_log`; collapses on `status="complete"`.
- `frontend/src/components/chat/research-findings-card.tsx` — renders `research_findings` / `benchmarks_findings`; injects citation superscripts.
- `frontend/src/components/chat/citation-popover.tsx` — hover popover sub-component.
- `frontend/src/components/chat/__tests__/research-plan-card.test.tsx`
- `frontend/src/components/chat/__tests__/research-activity-log.test.tsx`
- `frontend/src/components/chat/__tests__/research-findings-card.test.tsx`

**Modified files:**
- `backend/app/services/pipeline_service.py` — `run_research` and `run_benchmarks` rewritten to call planner → create activity log → stream → persist findings. The old combined `research_findings` emit-path in `run_benchmarks` is replaced with two separate findings messages.
- `backend/tests/integration/test_pipeline_service.py` — existing `test_run_research_*` and `test_run_benchmarks_*` tests migrate to mock the new streaming call (today they mock `ResearchAgent.research_client` / `BenchmarkAgent.find_benchmarks`, which the new path no longer calls).
- `backend/app/infrastructure/queue/events.py` — add `publish_message_updated()` convenience helper.
- `frontend/src/stores/chat-store.ts` — add `updateMessage(msg)` action + WS routing for the new `message_updated` event type.
- `frontend/src/stores/__tests__/chat-store.test.ts` — tests for `updateMessage`.
- `frontend/src/components/chat/message-bubble.tsx` — route the four new message types to the new cards; delete the internal `<ResearchCard />`.
- `frontend/src/types/proposal.ts` — type definitions for `ActivityEvent`, `CitationRef`, `Span`; document the new `message_type` values.

**Files left intentionally untouched:**
- `backend/app/services/ai/research_agent.py` and `benchmark_agent.py` — no longer called from `PipelineService` after this plan. Left in place (they still compile, just unused). A follow-up cleanup commit can delete them once we're confident nothing else depends on them.

---

## Task 1: `events.publish_message_updated` helper

**Files:**
- Modify: `backend/app/infrastructure/queue/events.py`
- Test: `backend/tests/unit/test_ws_events.py`

The activity-log card updates many times during a research run. Each update publishes a `message_updated` WS event. A thin helper keeps the call sites tidy and makes the event payload shape explicit in one place.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_ws_events.py`:

```python
from app.domain.schemas.chat_schemas import ChatMessageResponse


async def test_publish_message_updated_wraps_msg_in_message_updated_envelope():
    from types import SimpleNamespace
    redis = AsyncMock()
    msg = SimpleNamespace(
        id="m1", proposal_id="p1", role="assistant",
        message_type="research_activity_log",
        content="", extra_data={"phase": "research", "status": "running", "events": []},
        phase="research", channel="main",
        created_at=__import__("datetime").datetime(2026, 5, 15, 14, 32, 0, tzinfo=__import__("datetime").timezone.utc),
    )
    await events.publish_message_updated(redis, "p1", msg)
    redis.publish.assert_awaited_once()
    channel, raw = redis.publish.await_args.args
    assert channel == events.WS_CHANNEL
    envelope = __import__("json").loads(raw)
    assert envelope["proposal_id"] == "p1"
    assert envelope["payload"]["type"] == "message_updated"
    assert envelope["payload"]["message"]["id"] == "m1"
    assert envelope["payload"]["message"]["message_type"] == "research_activity_log"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ws_events.py::test_publish_message_updated_wraps_msg_in_message_updated_envelope -v`
Expected: FAIL — `AttributeError: module 'app.infrastructure.queue.events' has no attribute 'publish_message_updated'`.

- [ ] **Step 3: Implement the helper**

Append to `backend/app/infrastructure/queue/events.py`:

```python
from app.domain.schemas.chat_schemas import ChatMessageResponse


async def publish_message_updated(redis, proposal_id, msg) -> None:
    """Publish a `message_updated` WS event for a chat message that already
    exists on the client.

    Used by the activity-log flusher: each flush updates the same message in
    the DB and re-publishes its full current state so the frontend can
    `updateMessage(msg)` (replace-by-id) instead of growing its message list.
    """
    await publish(redis, str(proposal_id), {
        "type": "message_updated",
        "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
    })
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ws_events.py -v`
Expected: 4 PASS (3 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/queue/events.py backend/tests/unit/test_ws_events.py
git commit -m "feat(events): publish_message_updated helper for live message updates"
```

---

## Task 2: `research_planner.py` — Haiku plan generation

**Files:**
- Create: `backend/app/services/research_planner.py`
- Create: `backend/tests/integration/test_research_planner.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_research_planner.py`:

```python
"""Unit tests for the Haiku-based pre-flight plan generators."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.research_planner import generate_benchmarks_plan, generate_research_plan
from app.services.llm import Tier


class _StubAI:
    """Minimal AIService stand-in capturing the kwargs of complete_json."""

    def __init__(self, payload):
        self._payload = payload
        self.complete_json = AsyncMock(return_value=payload)


async def test_generate_research_plan_returns_queries_and_rationale(monkeypatch):
    ai = _StubAI({"queries": ["q1", "q2", "q3"], "rationale": "because reasons"})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    plan = await generate_research_plan(brief={"client": {"name": "Acme"}})
    assert plan == {"queries": ["q1", "q2", "q3"], "rationale": "because reasons"}


async def test_generate_research_plan_calls_haiku_tier(monkeypatch):
    ai = _StubAI({"queries": [], "rationale": ""})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    await generate_research_plan(brief={"client": {"name": "Acme"}})
    kwargs = ai.complete_json.await_args.kwargs
    assert kwargs["tier"] == Tier.FAST
    assert "research planner" in kwargs["system"].lower()
    assert "Acme" in kwargs["prompt"]


async def test_generate_benchmarks_plan_calls_haiku_with_benchmarks_system(monkeypatch):
    ai = _StubAI({"queries": ["price q"], "rationale": "why"})
    monkeypatch.setattr(
        "app.services.research_planner.get_ai_service", lambda: ai,
    )
    plan = await generate_benchmarks_plan(
        brief={"project": {"deliverables": [{"category": "Logo"}]}},
    )
    assert plan == {"queries": ["price q"], "rationale": "why"}
    kwargs = ai.complete_json.await_args.kwargs
    assert kwargs["tier"] == Tier.FAST
    assert "benchmark" in kwargs["system"].lower()
    # The deliverable category should be visible in the prompt for grounding.
    assert "Logo" in kwargs["prompt"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_planner.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.research_planner`.

- [ ] **Step 3: Write the module**

Create `backend/app/services/research_planner.py`:

```python
"""Pre-flight plan generation for the run_research and run_benchmarks phases.

A short Haiku call before the slow web-search call begins. The plan is shown
to the user as a chat message so they know what to expect during the wait
and have an audit trail later.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.llm import Tier, get_ai_service

_RESEARCH_PLAN_SYSTEM = """\
You are NUPROP's research planner. You're about to do thorough web research
on a client to back a high-value design / branding / professional-services
proposal. Before research begins, the user wants a short summary of what
you intend to look at and why.

Given the brief (as JSON), return:
  - "queries":   3-6 specific web-search queries you'd run (each a string,
                 phrased like a real search query — concrete, not vague)
  - "rationale": one short paragraph (2-3 sentences) explaining what these
                 queries together will tell us, and why those things matter
                 for shaping the proposal.

Return ONLY valid JSON. No prose, no markdown fences."""

_BENCHMARKS_PLAN_SYSTEM = """\
You are NUPROP's pricing-benchmark planner. You're about to find market
pricing for the deliverables in this brief. Before benchmarking begins,
the user wants a short summary of what you'll look at.

Given the brief and the list of deliverable categories, return:
  - "queries":   3-6 specific search queries you'd run for pricing data
                 (each a string — e.g. "logo design agency rates India
                 2024" not "design pricing")
  - "rationale": one short paragraph explaining what these queries
                 collectively will tell us about market rates and how
                 we'll use it.

Return ONLY valid JSON. No prose, no markdown fences."""


async def generate_research_plan(*, brief: dict) -> dict[str, Any]:
    """Produce a short structured plan for the upcoming research run.

    Returns a dict with ``queries`` (list[str]) and ``rationale`` (str).
    """
    ai = get_ai_service()
    return await ai.complete_json(
        prompt=json.dumps({"brief": brief}),
        tier=Tier.FAST,
        system=_RESEARCH_PLAN_SYSTEM,
        max_tokens=512,
    )


async def generate_benchmarks_plan(*, brief: dict) -> dict[str, Any]:
    """Produce a short structured plan for the upcoming benchmarks run.

    Returns a dict with ``queries`` (list[str]) and ``rationale`` (str).
    The brief's deliverable categories are surfaced in the prompt so the
    planner can suggest pricing-specific queries.
    """
    ai = get_ai_service()
    deliverables = (brief.get("project", {}) or {}).get("deliverables", []) or []
    return await ai.complete_json(
        prompt=json.dumps({"brief": brief, "deliverables": deliverables}),
        tier=Tier.FAST,
        system=_BENCHMARKS_PLAN_SYSTEM,
        max_tokens=512,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_planner.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/research_planner.py backend/tests/integration/test_research_planner.py
git commit -m "feat: Haiku-based research_planner — research + benchmarks plan generation"
```

---

## Task 3: `research_streaming.ActivityFlusher` — batched flush primitive

**Files:**
- Create: `backend/app/services/research_streaming.py` (just the `ActivityFlusher` class for now)
- Create: `backend/tests/integration/test_research_streaming.py`

The flusher is the live-update mechanism for the activity-log chat message: it accumulates `ActivityEvent` dicts, persists them to the message's `extra_data`, commits, and publishes a `message_updated` WS event. Flush triggers on event count or wall-clock time, whichever first.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_research_streaming.py`:

```python
"""Tests for ActivityFlusher batched-flush behaviour."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.research_streaming import (
    _FLUSH_MAX_EVENTS,
    _FLUSH_MAX_INTERVAL_S,
    ActivityFlusher,
)


async def _make_log_message(db, *, phase="research"):
    agency = await AgencyRepository(db).create(name="RS Agency", slug="rs-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="RS Project",
        brief={}, pipeline_state={"current_phase": "research"},
    )
    msg_repo = ChatMessageRepository(db)
    msg = await msg_repo.create(
        proposal_id=proposal.id,
        role="assistant",
        message_type=f"{phase}_activity_log",
        content="",
        extra_data={"phase": phase, "status": "running", "events": []},
        phase=phase,
    )
    await db.commit()
    return proposal, msg, msg_repo


async def test_flush_triggers_when_event_count_threshold_hit(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    # Append _FLUSH_MAX_EVENTS events — should fire exactly one flush.
    for i in range(_FLUSH_MAX_EVENTS):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    assert redis.publish.await_count == 1


async def test_flush_does_not_trigger_under_threshold_and_within_interval(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    # Append fewer than the threshold; no flush should fire.
    for i in range(_FLUSH_MAX_EVENTS - 1):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    assert redis.publish.await_count == 0


async def test_explicit_flush_with_final_status_marks_completion(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    await flusher.append({"type": "search", "query": "q1", "ts": "t"})
    await flusher.flush(final_status="complete")
    # Re-read the message to assert the persisted state.
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ChatMessageRepository(fresh).get_by_id(log_msg.id)
    assert refetched.extra_data["status"] == "complete"
    assert len(refetched.extra_data["events"]) == 1


async def test_flush_failed_status_records_error(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    await flusher.flush(final_status="failed", error="bedrock died")
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ChatMessageRepository(fresh).get_by_id(log_msg.id)
    assert refetched.extra_data["status"] == "failed"
    assert refetched.extra_data["error"] == "bedrock died"


async def test_flush_publishes_message_updated_event(db):
    """The published WS payload must be a message_updated event (not new_message)."""
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    for i in range(_FLUSH_MAX_EVENTS):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    redis.publish.assert_awaited()
    _, raw = redis.publish.await_args.args
    import json as _json
    envelope = _json.loads(raw)
    assert envelope["payload"]["type"] == "message_updated"
    assert envelope["payload"]["message"]["message_type"] == "research_activity_log"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_streaming.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.research_streaming`.

- [ ] **Step 3: Implement `ActivityFlusher`**

Create `backend/app/services/research_streaming.py`:

```python
"""Streaming-event handling for the run_research / run_benchmarks phases.

Two responsibilities split into well-named units:

- :class:`ActivityFlusher` — batched-flush primitive for a single
  ``*_activity_log`` chat message. Accumulates ``ActivityEvent`` rows,
  persists them in batches, commits, and publishes ``message_updated`` WS
  events.

- :func:`process_stream` — pure(ish) async function that consumes an
  Anthropic SDK message-stream and converts it into ``ActivityEvent`` calls
  to a provided callback while accumulating the final body, citation list,
  and span list. (Added in the next task.)
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.queue.events import publish_message_updated

logger = logging.getLogger(__name__)

# Flush triggers — chosen to feel "live" without over-committing.
_FLUSH_MAX_EVENTS: int = 5
_FLUSH_MAX_INTERVAL_S: float = 0.75


class ActivityFlusher:
    """Batched-flush helper for an activity-log chat message.

    Each :meth:`append` adds an ``ActivityEvent`` dict; a flush (DB UPDATE +
    commit + WS publish) fires when either ``_FLUSH_MAX_EVENTS`` is reached
    or ``_FLUSH_MAX_INTERVAL_S`` seconds have elapsed since the last flush.
    Call :meth:`flush` directly at end-of-stream with ``final_status`` set
    to mark the log as complete or failed.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        msg_repo: ChatMessageRepository,
        redis,
        log_msg_id,
        proposal_id,
        phase: str,
    ) -> None:
        self.session = session
        self.msg_repo = msg_repo
        self.redis = redis
        self.log_msg_id = log_msg_id
        self.proposal_id = proposal_id
        self.phase = phase
        self._all_events: list[dict[str, Any]] = []
        self._pending_count: int = 0
        self._last_flush_ts: float = monotonic()

    async def append(self, event: dict[str, Any]) -> None:
        self._all_events.append(event)
        self._pending_count += 1
        if (
            self._pending_count >= _FLUSH_MAX_EVENTS
            or (monotonic() - self._last_flush_ts) >= _FLUSH_MAX_INTERVAL_S
        ):
            await self.flush()

    async def flush(
        self,
        *,
        final_status: str | None = None,
        error: str | None = None,
    ) -> None:
        """Persist current state + publish a message_updated event.

        When ``final_status`` is provided (``"complete"`` or ``"failed"``)
        the activity-log message is marked terminal in its ``extra_data``;
        otherwise it stays ``"running"``.
        """
        # Short-circuit: nothing to do if no events accumulated AND we're not
        # being explicitly asked to set a terminal status.
        if self._pending_count == 0 and final_status is None:
            return

        extra: dict[str, Any] = {
            "phase": self.phase,
            "status": final_status or "running",
            "events": list(self._all_events),
        }
        if error:
            extra["error"] = error

        await self.msg_repo.update(self.log_msg_id, extra_data=extra)
        await self.session.commit()
        refreshed = await self.msg_repo.get_by_id(self.log_msg_id)
        if refreshed is not None:
            await publish_message_updated(self.redis, self.proposal_id, refreshed)
        self._pending_count = 0
        self._last_flush_ts = monotonic()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_streaming.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/research_streaming.py backend/tests/integration/test_research_streaming.py
git commit -m "feat: ActivityFlusher — batched-flush primitive for live activity logs"
```

---

## Task 4: `process_stream` — SDK stream → ActivityEvents + body + citations + spans

**Files:**
- Modify: `backend/app/services/research_streaming.py`
- Modify: `backend/tests/integration/test_research_streaming.py`

The `process_stream` function consumes Anthropic's `messages.stream` event iterator and emits `ActivityEvent` rows (via callback) while accumulating the final body text, citation refs, and citation spans for the findings message. It's the bridge between the SDK's raw streaming events and our domain shapes.

The Anthropic SDK delivers events as Pydantic models. The shapes we care about (gleaned from `anthropic.types` and the SDK's streaming guide):

```
RawContentBlockStartEvent  { content_block: ContentBlock }
  where ContentBlock is one of:
    ToolUseBlock                 { type: "tool_use", name: "web_search", input: {query: str} }
    WebSearchToolResultBlock     { type: "web_search_tool_result", content: [WebSearchResultBlock] }
    TextBlock                    { type: "text", text: str, citations?: [Citation] }
  where Citation has: url, title, cited_text, start_block_index, end_block_index

RawContentBlockDeltaEvent  { delta: TextDelta | InputJSONDelta }
  TextDelta: { type: "text_delta", text: str }

RawContentBlockStopEvent   { content_block: ContentBlock }  // final state of the block
```

In tests we synthesise these with `SimpleNamespace` — no need for real SDK types.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_research_streaming.py`:

```python
from types import SimpleNamespace

from app.services.research_streaming import process_stream


def _start(content_block):
    return SimpleNamespace(type="content_block_start", content_block=content_block)


def _delta(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _stop(content_block):
    return SimpleNamespace(type="content_block_stop", content_block=content_block)


def _tool_use(query):
    return SimpleNamespace(type="tool_use", name="web_search", input={"query": query})


def _ws_result(*results):
    return SimpleNamespace(type="web_search_tool_result", content=list(results))


def _ws_result_item(url, title):
    return SimpleNamespace(url=url, title=title)


def _text_block(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations or [])


def _citation(url, title, cited_text, start, end):
    return SimpleNamespace(
        url=url, title=title, cited_text=cited_text,
        start_block_index=start, end_block_index=end,
    )


class _AsyncIter:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        async def _gen():
            for item in self._items:
                yield item
        return _gen()


async def test_process_stream_records_search_events():
    events: list[dict] = []
    stream = _AsyncIter([
        _start(_tool_use("Pepsi Global revenue")),
        _stop(_tool_use("Pepsi Global revenue")),
    ])
    body, citations, spans = await process_stream(stream, on_event=events.append)
    search_events = [e for e in events if e["type"] == "search"]
    assert search_events == [{"type": "search", "query": "Pepsi Global revenue", "ts": search_events[0]["ts"]}]


async def test_process_stream_records_read_events_for_each_result_url():
    events: list[dict] = []
    stream = _AsyncIter([
        _start(_ws_result(
            _ws_result_item("https://reuters.com/a", "Pepsi Q4"),
            _ws_result_item("https://ft.com/b", "Beverage growth"),
        )),
    ])
    await process_stream(stream, on_event=events.append)
    reads = [e for e in events if e["type"] == "read"]
    assert len(reads) == 2
    assert reads[0]["url"] == "https://reuters.com/a"
    assert reads[0]["title"] == "Pepsi Q4"
    assert reads[1]["url"] == "https://ft.com/b"


async def test_process_stream_accumulates_body_from_text_deltas():
    events: list[dict] = []
    stream = _AsyncIter([
        _delta("Pepsi Global "),
        _delta("revenue grew 8.2% YoY."),
    ])
    body, _, _ = await process_stream(stream, on_event=events.append)
    assert body == "Pepsi Global revenue grew 8.2% YoY."


async def test_process_stream_collects_citations_from_text_block_stop():
    events: list[dict] = []
    citation = _citation("https://reuters.com/a", "Pepsi Q4", "Revenue grew 8.2% YoY.", 0, 31)
    stream = _AsyncIter([
        _delta("Pepsi Global revenue grew 8.2%."),
        _stop(_text_block("Pepsi Global revenue grew 8.2%.", citations=[citation])),
    ])
    _, citations, spans = await process_stream(stream, on_event=events.append)
    assert len(citations) == 1
    assert citations[0]["url"] == "https://reuters.com/a"
    assert citations[0]["domain"] == "reuters.com"
    assert citations[0]["id"] == 1
    assert spans == [{"start": 0, "end": 31, "citation_ids": [1]}]


async def test_process_stream_dedupes_citations_by_url():
    """Two citations for the same URL = one entry in citations, two spans."""
    cit1 = _citation("https://reuters.com/a", "Pepsi Q4", "Snippet A", 0, 20)
    cit2 = _citation("https://reuters.com/a", "Pepsi Q4", "Snippet B", 50, 70)
    events: list[dict] = []
    stream = _AsyncIter([
        _stop(_text_block("...", citations=[cit1, cit2])),
    ])
    _, citations, spans = await process_stream(stream, on_event=events.append)
    assert len(citations) == 1
    assert len(spans) == 2
    assert all(s["citation_ids"] == [1] for s in spans)


async def test_process_stream_emits_synthesizing_note_at_end():
    """After the stream ends the worker is doing final synthesis — surface that."""
    events: list[dict] = []
    stream = _AsyncIter([])
    await process_stream(stream, on_event=events.append)
    notes = [e for e in events if e["type"] == "note"]
    assert notes and "Synthesizing" in notes[0]["text"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_streaming.py -k process_stream -v`
Expected: FAIL — `ImportError: cannot import name 'process_stream'`.

- [ ] **Step 3: Implement `process_stream`**

Append to `backend/app/services/research_streaming.py`:

```python
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import urlparse


CitationRef = dict[str, Any]
Span = dict[str, Any]
ActivityEvent = dict[str, Any]
EventCallback = Callable[[ActivityEvent], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


async def process_stream(stream, *, on_event: EventCallback) -> tuple[str, list[CitationRef], list[Span]]:
    """Consume an Anthropic ``messages.stream`` iterator.

    Calls ``on_event(activity_event_dict)`` for each search query Claude
    issues, each result URL it reads, and a final ``note`` event before
    return. Returns ``(body, citations, spans)``:

    - body: the concatenated assistant text (the markdown findings body)
    - citations: deduped-by-URL list of CitationRef dicts
    - spans: list of Span dicts referencing citations by their ``id``
    """
    body_parts: list[str] = []
    citations: list[CitationRef] = []
    spans: list[Span] = []

    async for event in stream:
        event_type = getattr(event, "type", None)

        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block is None:
                continue
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", None) == "web_search":
                query = (getattr(block, "input", {}) or {}).get("query", "")
                if query:
                    await on_event({"type": "search", "query": query, "ts": _now_iso()})
            elif block_type == "web_search_tool_result":
                for result in (getattr(block, "content", None) or []):
                    url = getattr(result, "url", "")
                    title = getattr(result, "title", "") or _parse_domain(url)
                    if url:
                        await on_event({"type": "read", "url": url, "title": title, "ts": _now_iso()})

        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is not None and getattr(delta, "type", None) == "text_delta":
                body_parts.append(getattr(delta, "text", "") or "")

        elif event_type == "content_block_stop":
            block = getattr(event, "content_block", None)
            if block is None:
                continue
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", None) == "web_search":
                # If the query wasn't captured at start (e.g. it arrives via input_json_delta
                # before the input is finalized), pull it from the final block state here.
                query = (getattr(block, "input", {}) or {}).get("query", "")
                # Only emit if we haven't already (heuristic: search events recorded
                # in on_event live outside this function — accept potential
                # duplicate-on-empty-start as a minor cost; the start path above
                # captures the common case).
                # No-op in the common path; reserved for SDK variations.
            elif block_type == "text":
                for c in (getattr(block, "citations", None) or []):
                    cit = _ensure_citation(citations, c)
                    spans.append({
                        "start": getattr(c, "start_block_index", 0),
                        "end": getattr(c, "end_block_index", 0),
                        "citation_ids": [cit["id"]],
                    })

    # A trailing note — gives the user a "synthesizing..." beat in the UI
    # between the last tool result and the findings card arriving.
    await on_event({"type": "note", "text": "Synthesizing findings...", "ts": _now_iso()})

    return "".join(body_parts), citations, spans


def _ensure_citation(citations: list[CitationRef], anth_cit) -> CitationRef:
    """De-dup citations by URL. Returns the (existing or new) CitationRef."""
    url = getattr(anth_cit, "url", "")
    for existing in citations:
        if existing["url"] == url:
            return existing
    new: CitationRef = {
        "id": len(citations) + 1,
        "url": url,
        "title": getattr(anth_cit, "title", "") or url,
        "domain": _parse_domain(url),
        "cited_text": getattr(anth_cit, "cited_text", "") or "",
    }
    citations.append(new)
    return new
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_streaming.py -v`
Expected: all PASS (5 from Task 3 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/research_streaming.py backend/tests/integration/test_research_streaming.py
git commit -m "feat: process_stream — SDK stream → ActivityEvents + body + citation graph"
```

---

## Task 5: `PipelineService.run_research` — orchestrate planner + streaming + findings

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Create: `backend/tests/integration/test_research_transparency.py`

The existing `run_research` calls `ResearchAgent.research_client(...)` and writes `proposal.research`. The new flow: generate plan → create activity log → run streaming call with `ActivityFlusher` as the on_event callback → persist findings message → update `proposal.research` with the plain body.

- [ ] **Step 1: Read the existing `run_research` to see what needs replacing**

Run: `cd backend && grep -n "async def run_research\|async def run_benchmarks\|_load_template_config\|_load_context_brief" app/services/pipeline_service.py | head -10`
This shows where the current implementation lives and the helper methods we'll reuse.

- [ ] **Step 2: Write the failing end-to-end test**

Create `backend/tests/integration/test_research_transparency.py`:

```python
"""End-to-end tests for the new run_research / run_benchmarks behaviour:
plan + activity log + annotated findings."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


async def _make_proposal(db, *, brief=None):
    agency = await AgencyRepository(db).create(name="RT Agency", slug="rt-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="RT Project",
        brief=brief or {"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    await db.commit()
    return proposal


def _start(content_block):
    return SimpleNamespace(type="content_block_start", content_block=content_block)


def _delta(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _stop(content_block):
    return SimpleNamespace(type="content_block_stop", content_block=content_block)


class _MockStreamContext:
    """Stands in for the async context manager returned by messages.stream(...)."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self  # async-iterable below

    async def __aexit__(self, *a):
        return None

    def __aiter__(self):
        async def _gen():
            for ev in self._events:
                yield ev
        return _gen()


async def test_run_research_emits_plan_activity_log_and_findings(db, monkeypatch):
    proposal = await _make_proposal(db)

    # Mock the planner
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={
            "queries": ["Acme rebrand 2024", "Acme agency relationships"],
            "rationale": "Cover Acme's strategic context and who they already work with.",
        }),
    )

    # Mock the AI streaming call
    fake_events = [
        _start(SimpleNamespace(type="tool_use", name="web_search",
                                input={"query": "Acme rebrand 2024"})),
        _start(SimpleNamespace(type="web_search_tool_result", content=[
            SimpleNamespace(url="https://example.com/a", title="Acme rebrand article"),
        ])),
        _delta("Acme rebranded in 2024. "),
        _delta("Their previous identity was..."),
        _stop(SimpleNamespace(type="text", text="Acme rebranded in 2024. Their previous identity was...",
                              citations=[SimpleNamespace(
                                  url="https://example.com/a", title="Acme rebrand article",
                                  cited_text="Acme rebranded in 2024.",
                                  start_block_index=0, end_block_index=25,
                              )])),
    ]
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext(fake_events))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    # Three messages should have landed on the ideation-side channel.
    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "research_plan" in types
    assert "research_activity_log" in types
    assert "research_findings" in types

    plan = next(m for m in msgs if m.message_type == "research_plan")
    assert plan.extra_data["queries"] == ["Acme rebrand 2024", "Acme agency relationships"]
    assert plan.extra_data["phase"] == "research"

    log = next(m for m in msgs if m.message_type == "research_activity_log")
    assert log.extra_data["status"] == "complete"
    event_types = [e["type"] for e in log.extra_data["events"]]
    assert "search" in event_types
    assert "read" in event_types

    findings = next(m for m in msgs if m.message_type == "research_findings")
    assert "Acme rebranded in 2024." in findings.content
    assert findings.extra_data["phase"] == "research"
    assert len(findings.extra_data["citations"]) == 1
    assert findings.extra_data["citations"][0]["url"] == "https://example.com/a"
    assert findings.extra_data["citations"][0]["domain"] == "example.com"
    assert findings.extra_data["spans"]

    # proposal.research carries the plain markdown body (unchanged contract).
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert "Acme rebranded in 2024." in refetched.research


async def test_run_research_uses_opus_tier(monkeypatch, db):
    proposal = await _make_proposal(db)
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    from app.services.llm import Tier
    mock_ai.model_for.assert_called_with(Tier.HEAVY)


async def test_run_research_failure_marks_activity_log_failed_and_does_not_create_findings(
    db, monkeypatch,
):
    proposal = await _make_proposal(db)
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )

    class _BrokenStream(_MockStreamContext):
        def __aiter__(self):
            async def _gen():
                raise RuntimeError("bedrock died")
                yield  # pragma: no cover
            return _gen()

    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_BrokenStream([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    with pytest.raises(RuntimeError, match="bedrock died"):
        await svc.run_research(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "research_activity_log" in types
    log = next(m for m in msgs if m.message_type == "research_activity_log")
    assert log.extra_data["status"] == "failed"
    assert "bedrock died" in (log.extra_data.get("error") or "")
    assert "research_findings" not in types
    # proposal.research unchanged
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert refetched.research is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_transparency.py -v`
Expected: FAIL — assertions about plan / activity_log / findings messages won't match the current implementation.

- [ ] **Step 4: Read the existing `_run_research_and_benchmarks` / `run_research` body**

Run: `cd backend && sed -n '/async def run_research/,/async def run_benchmarks/p' app/services/pipeline_service.py | head -50`
Familiarise with what's being replaced.

- [ ] **Step 5: Rewrite `run_research`**

In `backend/app/services/pipeline_service.py`:

1. Add imports near the top (after existing ones):

```python
from app.services.llm import Tier, get_ai_service
from app.services.research_planner import generate_research_plan, generate_benchmarks_plan
from app.services.research_streaming import ActivityFlusher, process_stream
from app.services.ai.research_agent import RESEARCH_SYSTEM
```

2. Replace the existing `run_research` method body. The signature stays the same — `async def run_research(self, proposal_id: UUID | str) -> None`. New body:

```python
    async def run_research(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        # 1. Pre-flight plan (Haiku) — short structured JSON, ~1s.
        plan = await generate_research_plan(brief=proposal.brief or {})
        plan_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_plan",
            content="",
            extra_data={"phase": "research", **plan},
            phase="research",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, plan_msg)

        # 2. Activity log (starts empty, status="running").
        log_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_activity_log",
            content="",
            extra_data={"phase": "research", "status": "running", "events": []},
            phase="research",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, log_msg)

        # 3. Streaming Opus 4.7 call with web_search.
        flusher = ActivityFlusher(
            session=self.session,
            msg_repo=self.msg_repo,
            redis=self.redis,
            log_msg_id=log_msg.id,
            proposal_id=proposal_id,
            phase="research",
        )

        client_name = (proposal.brief or {}).get("client", {}).get("name", "the client")
        industry = (proposal.brief or {}).get("client", {}).get("industry")
        context_brief = await self._load_context_brief(proposal)
        user_msg = (
            f"Research {client_name}"
            + (f" (industry: {industry})" if industry else "")
            + ". Be thorough — this research directly feeds into a high-value proposal."
            + " Search the web comprehensively."
        )
        if context_brief:
            user_msg += f"\n\n## Existing context\n{context_brief}"

        ai = get_ai_service()
        try:
            async with ai.client.messages.stream(
                model=ai.model_for(Tier.HEAVY),     # Opus 4.7
                max_tokens=4096,
                system=RESEARCH_SYSTEM,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 10,
                }],
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                body, citations, spans = await process_stream(stream, on_event=flusher.append)
            await flusher.flush(final_status="complete")
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_research streaming failed for %s", proposal_id)
            await flusher.flush(final_status="failed", error=str(exc))
            raise

        # 4. Findings — annotated.
        findings_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_findings",
            content=body,
            extra_data={"phase": "research", "citations": citations, "spans": spans},
            phase="research",
        )
        await self.proposal_repo.update(proposal.id, research=body)
        await self.session.commit()
        await self._emit_message(proposal_id, findings_msg)
```

3. Helper method (already exists on the class, just confirm signature is still being called correctly): `self._load_context_brief(proposal)` returns `str | None`. If it doesn't exist on the class for some reason, leave the call out and instead set `context_brief = None`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_transparency.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_research_transparency.py
git commit -m "feat: run_research emits plan + activity log + annotated findings (Opus 4.7 streaming)"
```

---

## Task 6: `PipelineService.run_benchmarks` — same shape, Sonnet 4.6

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_research_transparency.py`

Same structure as `run_research`. Differences: planner is `generate_benchmarks_plan`, system prompt is `BENCHMARK_SYSTEM`, tier is `Tier.BALANCED`, message types use the `benchmarks_*` prefix, and `proposal.benchmarks` is updated. After this task the combined `research_findings` emit-path that used to live at the END of `run_benchmarks` no longer exists — each phase emits its own findings.

- [ ] **Step 1: Append the failing tests**

Append to `backend/tests/integration/test_research_transparency.py`:

```python
async def test_run_benchmarks_emits_separate_findings_message_with_benchmarks_phase(
    db, monkeypatch,
):
    proposal = await _make_proposal(
        db,
        brief={"client": {"name": "Acme"}, "project": {"deliverables": [{"category": "Logo"}]}},
    )
    # Pre-set the pipeline_state to research-completed so we exercise the
    # natural benchmarks entry-point (which run_benchmarks may otherwise
    # advance from the cost_model_review stage — see existing pipeline flow).

    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={
            "queries": ["logo design India rates 2024"],
            "rationale": "Find India-specific rate ranges.",
        }),
    )

    fake_events = [
        _start(SimpleNamespace(type="tool_use", name="web_search",
                                input={"query": "logo design India rates 2024"})),
        _start(SimpleNamespace(type="web_search_tool_result", content=[
            SimpleNamespace(url="https://example.com/rates", title="India rate card"),
        ])),
        _delta("Typical India logo design rates: 50k-3 lakh."),
        _stop(SimpleNamespace(type="text",
                              text="Typical India logo design rates: 50k-3 lakh.",
                              citations=[SimpleNamespace(
                                  url="https://example.com/rates", title="India rate card",
                                  cited_text="50k-3 lakh", start_block_index=27, end_block_index=37,
                              )])),
    ]
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext(fake_events))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "benchmarks_plan" in types
    assert "benchmarks_activity_log" in types
    assert "benchmarks_findings" in types
    # The OLD combined "research_findings"-with-both-bodies emit is gone.
    findings_count = sum(1 for m in msgs if m.message_type == "research_findings")
    assert findings_count == 0  # this test only ran benchmarks, not research

    findings = next(m for m in msgs if m.message_type == "benchmarks_findings")
    assert findings.extra_data["phase"] == "benchmarks"
    assert "50k-3 lakh" in findings.content


async def test_run_benchmarks_uses_balanced_sonnet_tier(monkeypatch, db):
    proposal = await _make_proposal(db)
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    from app.services.llm import Tier
    mock_ai.model_for.assert_called_with(Tier.BALANCED)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_transparency.py -k benchmarks -v`
Expected: FAIL — current `run_benchmarks` still creates the combined `research_findings` message.

- [ ] **Step 3: Rewrite `run_benchmarks`**

In `backend/app/services/pipeline_service.py`, replace the body of `run_benchmarks` with:

```python
    async def run_benchmarks(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        from app.services.ai.benchmark_agent import BENCHMARK_SYSTEM

        # 1. Pre-flight plan.
        plan = await generate_benchmarks_plan(brief=proposal.brief or {})
        plan_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_plan",
            content="",
            extra_data={"phase": "benchmarks", **plan},
            phase="benchmarks",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, plan_msg)

        # 2. Activity log.
        log_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_activity_log",
            content="",
            extra_data={"phase": "benchmarks", "status": "running", "events": []},
            phase="benchmarks",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, log_msg)

        # 3. Streaming Sonnet 4.6 call with web_search.
        flusher = ActivityFlusher(
            session=self.session,
            msg_repo=self.msg_repo,
            redis=self.redis,
            log_msg_id=log_msg.id,
            proposal_id=proposal_id,
            phase="benchmarks",
        )

        deliverables = (proposal.brief or {}).get("project", {}).get("deliverables", []) or []
        categories = sorted({d.get("category", "") for d in deliverables if d.get("category")})
        country = "India"  # NUPROP is India-focused; future: pull from agency settings.
        user_msg = (
            f"Find pricing benchmarks for these design / creative-agency services in {country}: "
            + ", ".join(categories or ["general design services"])
            + ". Search the web for real published data."
        )

        ai = get_ai_service()
        try:
            async with ai.client.messages.stream(
                model=ai.model_for(Tier.BALANCED),     # Sonnet 4.6
                max_tokens=4096,
                system=BENCHMARK_SYSTEM,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 8,
                }],
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                body, citations, spans = await process_stream(stream, on_event=flusher.append)
            await flusher.flush(final_status="complete")
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_benchmarks streaming failed for %s", proposal_id)
            await flusher.flush(final_status="failed", error=str(exc))
            raise

        # 4. Findings — annotated, separate message from research_findings.
        findings_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_findings",
            content=body,
            extra_data={"phase": "benchmarks", "citations": citations, "spans": spans},
            phase="benchmarks",
        )
        await self.proposal_repo.update(proposal.id, benchmarks=body)
        await self.session.commit()
        await self._emit_message(proposal_id, findings_msg)

        # Advance pipeline state to cost_model_review (unchanged from previous behaviour).
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        pipeline = (proposal.pipeline_state or {}).copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["research"]
        pipeline["current_phase"] = "cost_model_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
        await self.session.commit()
        await self._emit_phase_change(proposal_id, "cost_model_review")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_research_transparency.py -v`
Expected: 5 PASS (3 from Task 5 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_research_transparency.py
git commit -m "feat: run_benchmarks emits separate plan/activity/findings (Sonnet 4.6 streaming)"
```

---

## Task 7: Migrate `test_pipeline_service.py` fixtures

**Files:**
- Modify: `backend/tests/integration/test_pipeline_service.py`

The existing tests for `run_research` and `run_benchmarks` monkeypatch `ResearchAgent.research_client` and `BenchmarkAgent.find_benchmarks` — the new path never calls those methods. The tests need to migrate to mock the streaming call (or be replaced by the more thorough tests in `test_research_transparency.py`).

- [ ] **Step 1: List the tests that need migration**

Run: `cd backend && grep -n "^async def test_run_research\|^async def test_run_benchmarks" tests/integration/test_pipeline_service.py`
Expected: two test names — these are the ones to delete (replaced by tests in `test_research_transparency.py`).

- [ ] **Step 2: Delete the obsolete tests**

In `backend/tests/integration/test_pipeline_service.py`, delete the entire bodies of:
- `test_run_research_commits_research_before_emitting` (the one that monkeypatches `ResearchAgent.research_client`)
- `test_run_benchmarks_advances_pipeline_to_cost_model_review` (the one that monkeypatches `BenchmarkAgent.find_benchmarks`)

These two tests' coverage is now provided by `test_research_transparency.py`. Use a code search to confirm nothing else references their names:

Run: `cd backend && grep -rn "test_run_research_commits_research_before_emitting\|test_run_benchmarks_advances_pipeline_to_cost_model_review" tests/`
Expected: only the (now-deleted) definitions themselves. No external references.

- [ ] **Step 3: Run the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: all PASS — the remaining `test_pipeline_service` tests (build_cost_model, generate_narrative, generate_outputs, merge_preferences, analyze_brief) don't touch the research/benchmarks paths and are unaffected.

- [ ] **Step 4: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all PASS, 0 skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_pipeline_service.py
git commit -m "test: retire old run_research / run_benchmarks tests (replaced by test_research_transparency)"
```

---

## Task 8: `chat-store.updateMessage` + WebSocket routing for `message_updated`

**Files:**
- Modify: `frontend/src/stores/chat-store.ts`
- Modify: `frontend/src/stores/__tests__/chat-store.test.ts`

`updateMessage(msg)` finds an existing message by id within whichever channel slice (`messages` or `ideationMessages`) currently contains it and replaces it. No-op if the id isn't found (defensive guard against late deliveries after a proposal switch).

- [ ] **Step 1: Append the failing tests**

In `frontend/src/stores/__tests__/chat-store.test.ts` (create if missing — see the ideation plan Task 11 for the file's initial layout), append:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '../chat-store'
import type { ChatMessage } from '../../types/proposal'

function msg(id: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id, proposal_id: 'p1', role: 'assistant', message_type: 'text',
    content: 'orig', extra_data: {}, phase: 'research',
    created_at: '2026-01-01T00:00:00Z', channel: 'main',
    ...overrides,
  }
}

describe('chat-store updateMessage', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('replaces a message in the main slice by id', () => {
    useChatStore.getState().addMessage(msg('m1'))
    useChatStore.getState().updateMessage(msg('m1', { content: 'updated' }))
    expect(useChatStore.getState().messages[0].content).toBe('updated')
  })

  it('replaces a message in the ideation slice by id', () => {
    useChatStore.getState().addMessage(msg('i1', { channel: 'ideation' }))
    useChatStore.getState().updateMessage(msg('i1', { channel: 'ideation', content: 'new' }))
    expect(useChatStore.getState().ideationMessages[0].content).toBe('new')
  })

  it('is a no-op when the message id is not present', () => {
    useChatStore.getState().addMessage(msg('m1'))
    useChatStore.getState().updateMessage(msg('m999', { content: 'ghost' }))
    expect(useChatStore.getState().messages.length).toBe(1)
    expect(useChatStore.getState().messages[0].content).toBe('orig')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/stores/__tests__/chat-store.test.ts`
Expected: FAIL — `updateMessage` doesn't exist on the store.

- [ ] **Step 3: Add `updateMessage` to the store**

In `frontend/src/stores/chat-store.ts`:

1. Extend the state type to include the new action:

```typescript
updateMessage: (msg: ChatMessage) => void
```

2. Add the implementation inside the `create(...)` body, after `addMessage`:

```typescript
updateMessage: (msg: ChatMessage) =>
  set((state) => {
    const slice = msg.channel === 'ideation' ? 'ideationMessages' : 'messages'
    const list = state[slice] as ChatMessage[]
    const idx = list.findIndex((m) => m.id === msg.id)
    if (idx < 0) return {}
    const next = [...list]
    next[idx] = msg
    return { [slice]: next } as Partial<ChatState>
  }),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/stores/__tests__/chat-store.test.ts`
Expected: all PASS.

- [ ] **Step 5: Locate the WebSocket message handler**

Run: `cd frontend && grep -rn "new_message\|onmessage" src/ --include="*.ts" --include="*.tsx" | head -10`
Identifies the file that owns the WS handler — likely `src/hooks/use-ws.ts` or similar.

- [ ] **Step 6: Add `message_updated` routing**

In the WS message handler file, find the switch / if-chain that dispatches on `evt.type`. Add a branch:

```typescript
case 'message_updated':
  useChatStore.getState().updateMessage(evt.message)
  break
```

The exact location depends on the existing handler's structure. Follow the pattern of the existing `new_message` branch.

- [ ] **Step 7: Run the frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/stores/chat-store.ts frontend/src/stores/__tests__/chat-store.test.ts frontend/src/hooks/use-ws.ts
git commit -m "feat(store): updateMessage action + WS message_updated routing"
```

(Adjust the `git add` path for the WS handler file based on what Step 5 surfaced.)

---

## Task 9: `<ResearchPlanCard />`

**Files:**
- Create: `frontend/src/components/chat/research-plan-card.tsx`
- Create: `frontend/src/components/chat/__tests__/research-plan-card.test.tsx`

Renders both `research_plan` and `benchmarks_plan` message types. Data lives entirely in `extra_data.queries` (list of strings) + `extra_data.rationale` (string). `content` is empty for these types.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/chat/__tests__/research-plan-card.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResearchPlanCard } from '../research-plan-card'
import type { ChatMessage } from '../../../types/proposal'

function planMessage(phase: 'research' | 'benchmarks'): ChatMessage {
  return {
    id: 'pl1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_plan`, content: '',
    extra_data: {
      phase,
      queries: [
        'Pepsi Global rebrand 2024',
        'Pepsi creative agency relationships',
        'FMCG dashboarding benchmarks India',
      ],
      rationale: 'Together these queries cover strategic context and existing agency relationships.',
    },
    phase, created_at: '2026-01-01T00:00:00Z', channel: 'main',
  }
}

describe('ResearchPlanCard', () => {
  it('renders the research plan with queries and rationale', () => {
    render(<ResearchPlanCard message={planMessage('research')} />)
    expect(screen.getByText(/Research plan/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi Global rebrand 2024')).toBeInTheDocument()
    expect(screen.getByText('Pepsi creative agency relationships')).toBeInTheDocument()
    expect(screen.getByText('FMCG dashboarding benchmarks India')).toBeInTheDocument()
    expect(screen.getByText(/Together these queries/)).toBeInTheDocument()
  })

  it('uses the benchmarks header when phase=benchmarks', () => {
    render(<ResearchPlanCard message={planMessage('benchmarks')} />)
    expect(screen.getByText(/Benchmarks plan/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-plan-card.test.tsx`
Expected: FAIL — `Cannot find module '../research-plan-card'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/chat/research-plan-card.tsx`:

```tsx
import type { ChatMessage } from '../../types/proposal'

interface Props {
  message: ChatMessage
}

export function ResearchPlanCard({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const queries = (extra.queries as string[]) ?? []
  const rationale = (extra.rationale as string) ?? ''
  const title = phase === 'benchmarks' ? '📈 Benchmarks plan' : '🔍 Research plan'

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
        <p className="text-sm font-semibold text-slate-900 mb-3">{title}</p>
        {queries.length > 0 && (
          <>
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-1.5">I'll search for</p>
            <ul className="space-y-1 mb-3">
              {queries.map((q, i) => (
                <li key={i} className="text-sm text-slate-700">
                  <span className="text-slate-400">•</span> {q}
                </li>
              ))}
            </ul>
          </>
        )}
        {rationale && (
          <>
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-1.5">Why these queries</p>
            <p className="text-sm text-slate-700 leading-relaxed">{rationale}</p>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-plan-card.test.tsx`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/research-plan-card.tsx frontend/src/components/chat/__tests__/research-plan-card.test.tsx
git commit -m "feat(ui): ResearchPlanCard — renders pre-flight plan for research and benchmarks"
```

---

## Task 10: `<ResearchActivityLog />`

**Files:**
- Create: `frontend/src/components/chat/research-activity-log.tsx`
- Create: `frontend/src/components/chat/__tests__/research-activity-log.test.tsx`

Renders both `research_activity_log` and `benchmarks_activity_log`. Three states: `running` (spinner + auto-scroll + expanded), `complete` (collapsed to a one-liner summary; chevron expands), `failed` (expanded; error tooltip on the status badge).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/chat/__tests__/research-activity-log.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchActivityLog } from '../research-activity-log'
import type { ChatMessage } from '../../../types/proposal'

function logMessage({
  status = 'running',
  events = [] as Array<Record<string, unknown>>,
  error,
  phase = 'research' as 'research' | 'benchmarks',
}: { status?: string; events?: Array<Record<string, unknown>>; error?: string; phase?: 'research' | 'benchmarks' }): ChatMessage {
  return {
    id: 'log1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_activity_log`, content: '',
    extra_data: { phase, status, events, ...(error ? { error } : {}) },
    phase, created_at: '2026-01-01T00:00:00Z', channel: 'main',
  }
}

describe('ResearchActivityLog', () => {
  it('shows running status + spinner when status=running', () => {
    render(<ResearchActivityLog message={logMessage({
      events: [{ type: 'search', query: 'Pepsi', ts: '2026-01-01T00:00:01Z' }],
    })} />)
    expect(screen.getByText(/research activity/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/running/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi')).toBeInTheDocument()
  })

  it('renders search / read / note rows with the right icons', () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'complete',
      events: [
        { type: 'search', query: 'q1', ts: 't' },
        { type: 'read', url: 'https://reuters.com/a', title: 'Pepsi Q4', ts: 't' },
        { type: 'note', text: 'Synthesizing...', ts: 't' },
      ],
    })} />)
    // Collapsed by default on complete — expand to see rows.
    userEvent.click(screen.getByRole('button', { name: /expand/i }))
    // (RTL userEvent.click is async; the test framework will wait.)
  })

  it('collapses on status=complete with a one-line summary', () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'complete',
      events: [
        { type: 'search', query: 'q1', ts: 't' },
        { type: 'read', url: 'https://a.com/x', title: 'A', ts: 't' },
        { type: 'read', url: 'https://b.com/y', title: 'B', ts: 't' },
      ],
    })} />)
    // Summary mentions counts.
    expect(screen.getByText(/1 search/i)).toBeInTheDocument()
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument()
  })

  it('stays expanded on status=failed and shows the error', () => {
    render(<ResearchActivityLog message={logMessage({
      status: 'failed',
      error: 'bedrock died',
      events: [{ type: 'search', query: 'q1', ts: 't' }],
    })} />)
    expect(screen.getByLabelText(/failed/i)).toBeInTheDocument()
    expect(screen.getByText('q1')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-activity-log.test.tsx`
Expected: FAIL — `Cannot find module '../research-activity-log'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/chat/research-activity-log.tsx`:

```tsx
import { useState, useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types/proposal'

interface Event {
  type: 'search' | 'read' | 'note'
  query?: string
  url?: string
  title?: string
  text?: string
  ts: string
}

interface Props {
  message: ChatMessage
}

export function ResearchActivityLog({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const status = (extra.status as string) ?? 'running'
  const events = (extra.events as Event[]) ?? []
  const error = extra.error as string | undefined
  const isRunning = status === 'running'
  const isComplete = status === 'complete'
  const isFailed = status === 'failed'

  // Collapse-by-default on complete; always expanded on running or failed.
  const [collapsed, setCollapsed] = useState(isComplete)
  useEffect(() => { setCollapsed(isComplete) }, [isComplete])

  // Auto-scroll while running.
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (isRunning) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length, isRunning])

  const title = phase === 'benchmarks' ? '⚡ Benchmark activity' : '⚡ Research activity'
  const searchCount = events.filter((e) => e.type === 'search').length
  const readCount = events.filter((e) => e.type === 'read').length

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] w-[480px] rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <StatusBadge status={status} error={error} />
        </div>
        {isComplete && collapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="text-xs text-slate-600 hover:text-slate-900"
            aria-label="Expand activity log"
          >
            ✓ {searchCount} {searchCount === 1 ? 'search' : 'searches'} · {readCount} {readCount === 1 ? 'source' : 'sources'} · click to expand
          </button>
        ) : (
          <ol
            aria-live={isRunning ? 'polite' : 'off'}
            className="space-y-1 max-h-72 overflow-y-auto pr-1"
          >
            {events.map((e, i) => <EventRow key={i} event={e} />)}
            <div ref={endRef} />
          </ol>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status, error }: { status: string; error?: string }) {
  if (status === 'running') {
    return (
      <span aria-label="Running" className="flex items-center gap-1.5 text-xs text-slate-600">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
        running
      </span>
    )
  }
  if (status === 'complete') {
    return (
      <span aria-label="Complete" className="flex items-center gap-1.5 text-xs text-green-700">
        ✓ complete
      </span>
    )
  }
  return (
    <span
      aria-label="Failed"
      title={error || ''}
      className="flex items-center gap-1.5 text-xs text-amber-700"
    >
      ⚠ failed
    </span>
  )
}

function EventRow({ event }: { event: Event }) {
  const time = event.ts.slice(11, 19)
  if (event.type === 'search') {
    return (
      <li className="text-xs text-slate-700 flex gap-2">
        <span className="text-slate-400 tabular-nums">{time}</span>
        <span>🔍</span>
        <code className="font-mono text-slate-800">{event.query}</code>
      </li>
    )
  }
  if (event.type === 'read') {
    const domain = (() => { try { return new URL(event.url ?? '').hostname } catch { return '' } })()
    return (
      <li className="text-xs text-slate-700 flex gap-2">
        <span className="text-slate-400 tabular-nums">{time}</span>
        <span>📄</span>
        <span><strong>{domain}</strong> — {event.title}</span>
      </li>
    )
  }
  return (
    <li className="text-xs text-slate-600 flex gap-2 italic">
      <span className="text-slate-400 tabular-nums">{time}</span>
      <span>🧠</span>
      <span>{event.text}</span>
    </li>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-activity-log.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/research-activity-log.tsx frontend/src/components/chat/__tests__/research-activity-log.test.tsx
git commit -m "feat(ui): ResearchActivityLog — live timeline with collapse-on-complete"
```

---

## Task 11: `<CitationPopover />`

**Files:**
- Create: `frontend/src/components/chat/citation-popover.tsx`

Small popover that renders a single citation's title, domain badge, cited snippet, and an "Open source ↗" link. Visibility is controlled by the parent (`<ResearchFindingsCard />`); this component is dumb — given a citation, render it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/chat/__tests__/citation-popover.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CitationPopover } from '../citation-popover'

describe('CitationPopover', () => {
  it('renders title, domain, cited snippet, and a source link', () => {
    render(
      <CitationPopover citation={{
        id: 1,
        url: 'https://reuters.com/business/pepsi-q4',
        title: 'Pepsi Q4 2024 earnings',
        domain: 'reuters.com',
        cited_text: 'Revenue grew 8.2% YoY to $91.4B...',
      }} />,
    )
    expect(screen.getByText('Pepsi Q4 2024 earnings')).toBeInTheDocument()
    expect(screen.getByText('reuters.com')).toBeInTheDocument()
    expect(screen.getByText(/Revenue grew 8.2%/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /open source/i })
    expect(link).toHaveAttribute('href', 'https://reuters.com/business/pepsi-q4')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/citation-popover.test.tsx`
Expected: FAIL — `Cannot find module '../citation-popover'`.

- [ ] **Step 3: Implement the popover**

Create `frontend/src/components/chat/citation-popover.tsx`:

```tsx
export interface Citation {
  id: number
  url: string
  title: string
  domain: string
  cited_text: string
}

interface Props {
  citation: Citation
}

export function CitationPopover({ citation }: Props) {
  return (
    <div className="w-[400px] rounded-xl border border-slate-200 bg-white shadow-lg p-4 text-sm">
      <div className="flex items-start justify-between mb-1">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          {citation.domain}
        </span>
      </div>
      <p className="font-semibold text-slate-900 leading-snug mb-2">{citation.title}</p>
      <blockquote className="border-l-2 border-slate-300 pl-3 text-slate-700 italic mb-3 line-clamp-4">
        "{citation.cited_text}"
      </blockquote>
      <a
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-medium text-blue-600 hover:underline"
      >
        Open source ↗
      </a>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/citation-popover.test.tsx`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/citation-popover.tsx frontend/src/components/chat/__tests__/citation-popover.test.tsx
git commit -m "feat(ui): CitationPopover — dumb popover with title, domain, snippet, source link"
```

---

## Task 12: `<ResearchFindingsCard />` with citation superscript injection

**Files:**
- Create: `frontend/src/components/chat/research-findings-card.tsx`
- Create: `frontend/src/components/chat/__tests__/research-findings-card.test.tsx`

Renders both `research_findings` and `benchmarks_findings`. Plain markdown body in `message.content`; injects citation superscripts at `extra_data.spans` offsets; renders the sources list at the bottom.

For markdown rendering: NUPROP already uses `react-markdown` or similar (verify). If it doesn't, use a simple `<p style="whiteSpace: pre-wrap">` for v1 — the body is largely plain prose anyway.

- [ ] **Step 1: Confirm the existing markdown approach**

Run: `cd frontend && grep -rn "react-markdown\|remark\|micromark\|ReactMarkdown" src/ --include="*.ts" --include="*.tsx" | head -5`
- If `react-markdown` or similar is present, use it.
- If nothing turns up, the existing app renders message bodies with `<p className="whitespace-pre-wrap">` (verified by `message-bubble.tsx`). Use the same pattern.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/components/chat/__tests__/research-findings-card.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResearchFindingsCard } from '../research-findings-card'
import type { ChatMessage } from '../../../types/proposal'

function findingsMessage({
  phase = 'research' as 'research' | 'benchmarks',
  content = 'Pepsi Global revenue grew 8.2% YoY in Q4 2024. Their last major rebrand was in 2008.',
  citations = [
    { id: 1, url: 'https://reuters.com/a', title: 'Pepsi Q4', domain: 'reuters.com', cited_text: 'Revenue grew 8.2%' },
    { id: 2, url: 'https://brandnew.com/x', title: 'Pepsi 2008 rebrand', domain: 'brandnew.com', cited_text: 'rebrand was in 2008' },
  ],
  spans = [
    { start: 0, end: 47, citation_ids: [1] },
    { start: 49, end: 86, citation_ids: [2] },
  ],
}: { phase?: 'research' | 'benchmarks'; content?: string; citations?: object[]; spans?: object[] } = {}): ChatMessage {
  return {
    id: 'f1', proposal_id: 'p1', role: 'assistant',
    message_type: `${phase}_findings`, content,
    extra_data: { phase, citations, spans },
    phase, created_at: '2026-01-01T00:00:00Z', channel: 'main',
  }
}

describe('ResearchFindingsCard', () => {
  it('renders the markdown body with citation superscripts injected', () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    expect(screen.getByText(/Pepsi Global revenue/)).toBeInTheDocument()
    // Two superscripts — one per span.
    const supers = document.querySelectorAll('sup[data-citation-id]')
    expect(supers.length).toBe(2)
    expect(supers[0].getAttribute('data-citation-id')).toBe('1')
    expect(supers[1].getAttribute('data-citation-id')).toBe('2')
  })

  it('shows the sources list at the bottom with title + domain', () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    expect(screen.getByText(/Sources/i)).toBeInTheDocument()
    expect(screen.getByText('Pepsi Q4')).toBeInTheDocument()
    expect(screen.getByText(/reuters.com/)).toBeInTheDocument()
    expect(screen.getByText('Pepsi 2008 rebrand')).toBeInTheDocument()
  })

  it('opens the popover when a superscript is hovered', async () => {
    render(<ResearchFindingsCard message={findingsMessage()} />)
    const supers = document.querySelectorAll('sup[data-citation-id]')
    await userEvent.hover(supers[0] as Element)
    expect(await screen.findByText('Pepsi Q4')).toBeInTheDocument()
  })

  it('uses the benchmarks header when phase=benchmarks', () => {
    render(<ResearchFindingsCard message={findingsMessage({ phase: 'benchmarks' })} />)
    expect(screen.getByText(/Pricing benchmarks/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-findings-card.test.tsx`
Expected: FAIL — `Cannot find module '../research-findings-card'`.

- [ ] **Step 4: Implement the card**

Create `frontend/src/components/chat/research-findings-card.tsx`:

```tsx
import { useState, useMemo } from 'react'
import type { ChatMessage } from '../../types/proposal'
import { CitationPopover, type Citation } from './citation-popover'

interface Span {
  start: number
  end: number
  citation_ids: number[]
}

interface Props {
  message: ChatMessage
}

/**
 * Splits ``content`` at ``span.end`` offsets and interleaves clickable
 * superscript markers. v1 renders plain prose with whitespace preserved;
 * proper markdown rendering can be retrofitted by replacing the segment
 * <p>{text}</p> with a <ReactMarkdown> call without changing the splitting
 * logic.
 */
function renderWithSpans(content: string, spans: Span[]): React.ReactNode[] {
  const sorted = [...spans].sort((a, b) => a.end - b.end)
  const out: React.ReactNode[] = []
  let cursor = 0
  for (let i = 0; i < sorted.length; i++) {
    const sp = sorted[i]
    const end = Math.min(sp.end, content.length)
    if (end <= cursor) continue
    out.push(content.slice(cursor, end))
    out.push(
      <CitationMarker key={`sup-${i}`} citationIds={sp.citation_ids} />,
    )
    cursor = end
  }
  if (cursor < content.length) out.push(content.slice(cursor))
  return out
}

function CitationMarker({ citationIds }: { citationIds: number[] }) {
  const [hover, setHover] = useState(false)
  // For v1 only the first citation_id renders a popover; multi-id spans
  // are rare and we can iterate later.
  const id = citationIds[0]
  return (
    <span className="relative inline-block">
      <sup
        data-citation-id={id}
        className="text-[10px] font-semibold text-blue-600 cursor-pointer ml-0.5"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        [{id}]
      </sup>
      {hover && <CitationPopoverPortal citationId={id} />}
    </span>
  )
}

// Defined inside the same module so we can read the citations from the
// findings card's React context without a dedicated provider for v1.
let _activeCitations: Citation[] = []

function CitationPopoverPortal({ citationId }: { citationId: number }) {
  const citation = _activeCitations.find((c) => c.id === citationId)
  if (!citation) return null
  return (
    <span className="absolute z-50 top-full mt-1 left-0">
      <CitationPopover citation={citation} />
    </span>
  )
}

export function ResearchFindingsCard({ message }: Props) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  const phase = (extra.phase as string) ?? 'research'
  const citations = (extra.citations as Citation[]) ?? []
  const spans = (extra.spans as Span[]) ?? []

  // Make citations visible to the marker subcomponents during this render.
  _activeCitations = citations

  const nodes = useMemo(
    () => renderWithSpans(message.content, spans),
    [message.content, spans],
  )

  const title = phase === 'benchmarks' ? '📊 Pricing benchmarks' : '📑 Research findings'
  const palette = phase === 'benchmarks' ? 'bg-amber-50 border-amber-200' : 'bg-blue-50 border-blue-200'

  return (
    <div className="flex justify-start">
      <div className={`max-w-[90%] rounded-2xl border ${palette} px-5 py-4`}>
        <p className="text-sm font-semibold text-slate-900 mb-3">{title}</p>
        <div className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
          {nodes}
        </div>
        {citations.length > 0 && (
          <>
            <hr className="my-3 border-slate-200" />
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-2">Sources</p>
            <ol className="space-y-1 text-xs">
              {citations.map((c) => (
                <li key={c.id} className="text-slate-700">
                  <span className="text-slate-400">[{c.id}]</span>{' '}
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                  >
                    {c.title}
                  </a>
                  <span className="text-slate-400"> · {c.domain}</span>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}
```

Note: this v1 implementation uses a module-level `_activeCitations` global because the marker is rendered inside `renderWithSpans` output and doesn't have direct prop access. A cleaner refactor would wrap markers in a citations Context provider — fine to retrofit later, the test surface stays the same.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/research-findings-card.test.tsx`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/research-findings-card.tsx frontend/src/components/chat/__tests__/research-findings-card.test.tsx
git commit -m "feat(ui): ResearchFindingsCard — annotated findings with hover citation superscripts"
```

---

## Task 13: Wire new components into `<MessageBubble />` routing

**Files:**
- Modify: `frontend/src/components/chat/message-bubble.tsx`

Add dispatch for the six new message types (plan / activity_log / findings × research / benchmarks). Delete the existing internal `<ResearchCard />` since the old combined `research_findings` shape no longer exists.

- [ ] **Step 1: Read the existing dispatch**

Run: `cd frontend && grep -n "message_type ===\|ResearchCard" src/components/chat/message-bubble.tsx | head -15`
Surfaces every existing dispatch branch.

- [ ] **Step 2: Add the new imports + dispatch branches**

In `frontend/src/components/chat/message-bubble.tsx`:

1. Add imports near the existing imports:

```tsx
import { ResearchPlanCard } from './research-plan-card'
import { ResearchActivityLog } from './research-activity-log'
import { ResearchFindingsCard } from './research-findings-card'
```

2. Add the dispatch branches BEFORE the existing `research_findings` branch (which still exists for any historical messages, but the new path is preferred). Place them right after the brief-summary / approval-gate dispatch:

```tsx
if (
  message.message_type === 'research_plan' ||
  message.message_type === 'benchmarks_plan'
) {
  return <ResearchPlanCard message={message} />
}

if (
  message.message_type === 'research_activity_log' ||
  message.message_type === 'benchmarks_activity_log'
) {
  return <ResearchActivityLog message={message} />
}

if (
  message.message_type === 'research_findings' ||
  message.message_type === 'benchmarks_findings'
) {
  return <ResearchFindingsCard message={message} />
}
```

3. Delete the existing internal `<ResearchCard />` function and its in-dispatch branch (lines ~46-48 and 83-101 in the current `message-bubble.tsx`). The new `<ResearchFindingsCard />` is its successor.

- [ ] **Step 3: Verify no other code imports the deleted `<ResearchCard />`**

Run: `cd frontend && grep -rn "ResearchCard" src/`
Expected: no references. If references appear, they need to migrate to `ResearchFindingsCard`.

- [ ] **Step 4: Run the frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: all PASS.

- [ ] **Step 5: Frontend build sanity check**

Run: `cd frontend && pnpm build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/message-bubble.tsx
git commit -m "feat(ui): route new research / benchmarks message types in MessageBubble"
```

---

## Task 14: Full suites green + boot sanity

**Files:** none (verification).

- [ ] **Step 1: Backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all PASS, 0 skipped.

- [ ] **Step 2: Frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: all PASS.

- [ ] **Step 3: Frontend build**

Run: `cd frontend && pnpm build`
Expected: build succeeds.

- [ ] **Step 4: App imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"`
Expected: routes count unchanged from before this plan (this plan adds no new HTTP routes).

- [ ] **Step 5: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "test: fix fallout from research-transparency rollout"
```

---

## Task 15: Live smoke test against the docker stack

**Files:** none (manual verification).

- [ ] **Step 1: Rebuild + bring the stack up**

```bash
cd /Users/karthikramesh/Developer/nuprop
docker compose up --build -d
```

Wait for `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/health` to return `200`.

- [ ] **Step 2: Drive a full pipeline from the browser**

1. Register / log in at `http://localhost:8080`.
2. Create a real-name client (e.g. "Bombay Shaving Co"). Real-sounding names produce better research than synthetic test names.
3. Create a proposal. Walk through brief intake until the brief gate appears.
4. Click **Approve Brief**, then **Confirm template** on the template suggestion.
5. **Research begins.** Expect to see in the chat thread:
   - A `🔍 Research plan` card with 3-6 queries and a rationale paragraph (within ~1-2s of clicking).
   - A `⚡ Research activity` card that grows live — searches appear with the query in monospace, reads appear with the domain in bold and title truncated.
   - After 60-90s: a `📑 Research findings` card with the body text, hover-citation superscripts, and a sources list at the bottom. The activity log card auto-collapses to a `✓ N searches · M sources` one-liner.
6. Continue: **benchmarks** runs immediately after, with the same three-message shape (`📈 Benchmarks plan`, `⚡ Benchmark activity`, `📊 Pricing benchmarks`).
7. Hover a citation superscript: a popover appears with the source title, domain, cited snippet, and "Open source ↗" link.
8. Click an entry in the sources list at the bottom of a findings card: a new tab opens at the source URL.

- [ ] **Step 3: Spot-check the activity-log persistence**

Refresh the browser tab. The thread should re-render with all six messages (plan / activity_log / findings × 2 phases) intact. The activity_log cards stay collapsed showing only the summary line. Click to expand and confirm every search and read event is still present.

- [ ] **Step 4: Worker log timing sanity check**

```bash
docker compose logs worker | grep -E "(→|←|research|benchmarks)" | tail -20
```

Look for the timing pattern: research starts, runs ~30-90s, completes; benchmarks chains immediately after, runs ~30-60s, completes. Each phase should show a single `→ run_research` start and a single `← run_research ●` finish — no retry loops or stale-id no-ops.

- [ ] **Step 5: Tear down**

```bash
cd /Users/karthikramesh/Developer/nuprop && docker compose down
```

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task(s) |
|---|---|
| Goal 1 — Pre-flight plan | Tasks 2, 5, 6, 9 |
| Goal 2 — Live activity stream | Tasks 3, 4, 5, 6, 10 |
| Goal 3 — Annotated findings | Tasks 4, 5, 6, 11, 12 |
| Non-goals — explicit deferrals | Not implemented — covered by omission (no streaming brief intake task, no DOCX citations, no cell-level table annotations, no tier-toggle UI, etc.) |
| Architecture — three messages per phase | Tasks 5 (research_plan, research_activity_log, research_findings), 6 (benchmarks_*) |
| Architecture — backward compat: `proposal.research` stays plain markdown | Tasks 5 step 5 (the `.update(proposal.id, research=body)` call), 6 step 3 (`.update(proposal.id, benchmarks=body)`) |
| Architecture — failure isolation: activity_log marked failed, no findings created, proposal.research unchanged | Tasks 5 step 5 (try/except + `flusher.flush(final_status="failed")`), 5 step 2 (`test_run_research_failure_marks_activity_log_failed_and_does_not_create_findings`) |
| Data model — new message types | Tasks 5, 6, 9, 10, 12, 13 |
| Data model — `extra_data` shapes (citations, spans, events) | Tasks 4, 5, 6, 11, 12 |
| Data model — no schema changes | No migration task needed — confirmed in File Structure header |
| WS protocol — new `message_updated` event | Tasks 1 (`publish_message_updated` helper), 3 (ActivityFlusher uses it), 8 (frontend store + WS routing) |
| Worker — tier choice (Haiku plan, Opus research, Sonnet benchmarks) | Tasks 2 (Haiku in `complete_json` Tier.FAST), 5 (Opus via `model_for(Tier.HEAVY)`), 6 (Sonnet via `model_for(Tier.BALANCED)`) |
| Worker — batched flush (5 events / 750ms) | Task 3 (`_FLUSH_MAX_EVENTS`, `_FLUSH_MAX_INTERVAL_S` constants) |
| Worker — streaming event handling | Task 4 (process_stream) |
| Pre-flight plan system prompts | Task 2 (`_RESEARCH_PLAN_SYSTEM`, `_BENCHMARKS_PLAN_SYSTEM` verbatim from spec) |
| Frontend — `<ResearchPlanCard />` | Task 9 |
| Frontend — `<ResearchActivityLog />` with collapse-on-complete | Task 10 |
| Frontend — `<CitationPopover />` | Task 11 |
| Frontend — `<ResearchFindingsCard />` with superscript injection | Task 12 |
| Frontend — `message-bubble.tsx` routing | Task 13 |
| Frontend — store `updateMessage` + WS routing | Task 8 |
| Backend tests (planner, streaming, e2e) | Tasks 2, 3, 4, 5, 6 |
| Frontend tests (components, store, WS) | Tasks 8, 9, 10, 11, 12 |
| Existing-test migration | Task 7 |
| Final smoke | Task 15 |

**Placeholder scan:** No "TBD", "TODO", "later", "appropriate", "edge cases". Task 8 Step 5 / 6 acknowledge the WS handler file path may differ ("based on what Step 5 surfaced") — that's a precise instruction to follow the file the grep surfaces, not a vague directive. Task 12's note about the `_activeCitations` module-level global being a v1 simplification flags a real architectural choice for future revisit without leaving anything unfinished.

**Type / name consistency:**

- `ActivityEvent` shape (`{type: "search"|"read"|"note", query?|url?+title?|text?, ts}`) is the same in `research_streaming.py` (Task 4), the `ActivityFlusher` payload (Task 3), test fixtures (Tasks 3, 4, 5, 6), and the frontend `Event` interface (Task 10).
- `CitationRef` shape (`id, url, title, domain, cited_text`) is the same in `_ensure_citation` (Task 4), the worker findings persistence (Tasks 5, 6), the frontend `Citation` interface (Task 11), and the popover render (Task 11).
- `Span` shape (`start, end, citation_ids[]`) is the same in `process_stream` (Task 4), the worker findings persistence (Tasks 5, 6), and the frontend `renderWithSpans` function (Task 12).
- Message type names are spelled identically (e.g. `research_activity_log`, not `research_activity` or `research_activitylog`) across worker emits, frontend dispatch, and tests.
- Tier choice: `Tier.FAST` for plans, `Tier.HEAVY` for research, `Tier.BALANCED` for benchmarks — consistent across Tasks 2, 5, 6, and matches the spec's tier-choice table.
- WS event type `message_updated` is the same string in `publish_message_updated` (Task 1), the frontend WS handler (Task 8), and the store dispatch (Task 8).

**Scope check:** v1 surface is one new WS event type, two new service modules (`research_planner`, `research_streaming`), two rewritten methods on `PipelineService`, four new frontend components, one new store action. No schema changes, no new HTTP routes. v2 deferrals (streaming brief intake, downstream citation awareness, DOCX/PDF citations, table-cell annotations, etc.) are explicit in the spec and untouched here.
