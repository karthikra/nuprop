# Background-Worker Proposal Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the multi-phase proposal pipeline off the HTTP request thread onto ARQ background jobs so each phase commits its DB writes before it broadcasts — fixing the read-your-writes bug.

**Architecture:** Gate-approval routes validate, create an ack message, enqueue the first phase job, and return immediately. An ARQ worker process runs each phase in its own `AsyncSession` that commits before publishing a WebSocket event to a Redis pub/sub channel; the API process subscribes to that channel and relays to its local WebSocket connections. Pipeline logic is extracted from the 832-line `ChatViewModel` into a session-parameterised `PipelineService`.

**Tech Stack:** FastAPI, async SQLAlchemy, ARQ (Redis task queue), `redis.asyncio` (pub/sub), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-15-background-worker-pipeline-design.md`

---

## File Structure

**New files:**
- `backend/app/infrastructure/queue/redis.py` — ARQ `RedisSettings` + pool lifecycle helpers.
- `backend/app/infrastructure/queue/events.py` — `publish()` (push WS event to Redis) + `ws_event_subscriber()` (relay to `ws_manager`).
- `backend/app/services/pipeline_service.py` — the pipeline phase logic, extracted from `ChatViewModel`, session-parameterised.
- `backend/app/workers/pipeline.py` — the 6 ARQ task functions + `WorkerSettings`.
- `backend/tests/integration/test_pipeline_service.py` — per-phase logic tests.
- `backend/tests/integration/test_pipeline_worker.py` — ARQ task tests (job_status, chaining, retry-to-failed).
- `backend/tests/unit/test_ws_events.py` — `publish` / `ws_event_subscriber` bridge test.

**Modified files:**
- `backend/pyproject.toml` — add `arq` dependency.
- `backend/app/core/config.py` — add `ARQ_MAX_TRIES`.
- `backend/app/main.py` — `lifespan` starts the ARQ pool + WS subscriber.
- `backend/app/viewmodels/chat_viewmodel.py` — slim to validate + enqueue; pipeline methods removed.
- `backend/app/views/v1/chat.py` — `send_message` returns `[user_msg]`; add `POST /chat/{id}/retry`.
- `backend/tests/conftest.py` — mock ARQ pool fixture + `events.publish` spy.
- `backend/tests/integration/test_persistence_bug.py` — rewritten from `skip` to a real passing test.
- `backend/tests/integration/test_chat_api.py` — `approve_gate`/`send_message` now assert enqueue, not inline execution.
- `frontend/src/api/proposals.ts` — `useSendMessage` return type.
- `frontend/src/pages/proposals/builder.tsx` — consume `[user_msg]` only.
- `docker-compose.yml`, `fly.toml` — Redis + worker process.

---

## Task 1: Add ARQ dependency and config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add `arq` to dependencies**

In `backend/pyproject.toml`, add to the `dependencies` array (alphabetical, after `anthropic`):

```toml
    "arq>=0.26.3",
```

- [ ] **Step 2: Install**

Run: `cd backend && uv pip install --break-system-packages arq`
Expected: `arq` installed; `.venv/bin/python -c "import arq; print(arq.__version__)"` prints a version.

- [ ] **Step 3: Add ARQ config knob**

In `backend/app/core/config.py`, after the Redis block (`REDIS_URL`), add:

```python
    ARQ_MAX_TRIES: int = 3
```

- [ ] **Step 4: Verify config loads**

Run: `cd backend && .venv/bin/python -c "from app.core.config import get_settings; print(get_settings().ARQ_MAX_TRIES)"`
Expected: `3`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py
git commit -m "chore: add arq dependency and ARQ_MAX_TRIES config"
```

---

## Task 2: ARQ Redis settings module

**Files:**
- Create: `backend/app/infrastructure/queue/redis.py`

- [ ] **Step 1: Write the module**

Create `backend/app/infrastructure/queue/redis.py`:

```python
"""ARQ Redis connection settings and pool lifecycle.

The API process holds one ARQ pool (created in ``app.main`` lifespan) used to
enqueue jobs and to publish WebSocket events. The worker process gets its own
connection from ARQ via the task ``ctx['redis']``.
"""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings


def get_redis_settings() -> RedisSettings:
    """ARQ RedisSettings parsed from the configured REDIS_URL."""
    return RedisSettings.from_dsn(get_settings().REDIS_URL)


async def create_arq_pool() -> ArqRedis:
    """Create an ARQ pool — used by the API process to enqueue jobs."""
    return await create_pool(get_redis_settings())
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && .venv/bin/python -c "from app.infrastructure.queue.redis import get_redis_settings; print(get_redis_settings())"`
Expected: prints a `RedisSettings(...)` repr, no error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/queue/redis.py
git commit -m "feat: ARQ redis settings and pool factory"
```

---

## Task 3: WebSocket events module (publish + subscriber)

**Files:**
- Create: `backend/app/infrastructure/queue/events.py`
- Test: `backend/tests/unit/test_ws_events.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_ws_events.py`:

```python
"""Unit tests for the Redis pub/sub WebSocket bridge."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.queue import events

WS_CHANNEL = "nuprop:ws"


async def test_publish_pushes_a_json_envelope_to_the_channel():
    redis = AsyncMock()
    await events.publish(redis, "prop-1", {"type": "phase_change", "phase": "research"})
    redis.publish.assert_awaited_once()
    channel, raw = redis.publish.await_args.args
    assert channel == WS_CHANNEL
    envelope = json.loads(raw)
    assert envelope == {
        "proposal_id": "prop-1",
        "payload": {"type": "phase_change", "phase": "research"},
    }


async def test_handle_event_relays_to_ws_manager(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(events.ws_manager, "broadcast", broadcast)
    raw = json.dumps({"proposal_id": "prop-9", "payload": {"type": "typing", "typing": True}})
    await events._handle_event(raw)
    broadcast.assert_awaited_once_with("prop-9", {"type": "typing", "typing": True})


async def test_handle_event_ignores_malformed_payloads(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(events.ws_manager, "broadcast", broadcast)
    await events._handle_event("not-json{")  # must not raise
    broadcast.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ws_events.py -v`
Expected: FAIL — `ModuleNotFoundError: app.infrastructure.queue.events`

- [ ] **Step 3: Write the module**

Create `backend/app/infrastructure/queue/events.py`:

```python
"""Redis pub/sub bridge for WebSocket events.

The worker runs in a separate process and cannot reach the API process's
in-memory ``ws_manager``. Every WS emit is published to the ``nuprop:ws`` Redis
channel; the API process runs ``ws_event_subscriber`` (started in lifespan) which
relays each event to its locally-held WebSocket connections.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

WS_CHANNEL = "nuprop:ws"


async def publish(redis, proposal_id: str, payload: dict) -> None:
    """Publish a WebSocket event for a proposal onto the shared Redis channel.

    ``redis`` is any redis client with an async ``publish`` — the ARQ pool in the
    API process, or ``ctx['redis']`` in a worker task.
    """
    envelope = json.dumps({"proposal_id": str(proposal_id), "payload": payload})
    await redis.publish(WS_CHANNEL, envelope)


async def _handle_event(raw: str | bytes) -> None:
    """Relay one received pub/sub message to the local ws_manager."""
    try:
        envelope = json.loads(raw)
        proposal_id = envelope["proposal_id"]
        payload = envelope["payload"]
    except (ValueError, KeyError, TypeError):
        logger.warning("dropping malformed ws event: %r", raw)
        return
    await ws_manager.broadcast(proposal_id, payload)


async def ws_event_subscriber() -> None:
    """Long-lived task: subscribe to the WS channel and relay to ws_manager.

    Started as an asyncio task in ``app.main`` lifespan. Reconnects on error.
    """
    while True:
        client = aioredis.from_url(get_settings().REDIS_URL)
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(WS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    await _handle_event(message["data"])
        except asyncio.CancelledError:
            await client.aclose()
            raise
        except Exception:  # noqa: BLE001 — keep the subscriber alive
            logger.exception("ws subscriber error; reconnecting in 2s")
            await client.aclose()
            await asyncio.sleep(2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ws_events.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/queue/events.py backend/tests/unit/test_ws_events.py
git commit -m "feat: redis pub/sub WebSocket event bridge"
```

---

## Task 4: Wire ARQ pool + WS subscriber into app lifespan

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Update lifespan**

In `backend/app/main.py`, replace the `lifespan` function. Add imports at the top of the file (after the existing imports):

```python
import asyncio

from app.infrastructure.queue.events import ws_event_subscriber
from app.infrastructure.queue.redis import create_arq_pool
```

Replace the `lifespan` body with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (dev only — production uses Alembic)
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Seed system templates (idempotent — all environments)
    async with async_session_factory() as db:
        count = await seed_templates(db)
        if count:
            await db.commit()

    # Background-worker plumbing: ARQ pool for enqueueing + WS event subscriber
    app.state.arq_pool = await create_arq_pool()
    app.state.ws_subscriber_task = asyncio.create_task(ws_event_subscriber())

    yield

    app.state.ws_subscriber_task.cancel()
    try:
        await app.state.ws_subscriber_task
    except asyncio.CancelledError:
        pass
    await app.state.arq_pool.aclose()
    await engine.dispose()
```

- [ ] **Step 2: Verify the app still imports and boots**

Run:
```bash
cd backend && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"
```
Expected: prints `routes: 61`, no error. (Lifespan is not executed by a bare import.)

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: start ARQ pool and WS subscriber in app lifespan"
```

---

## Task 5: PipelineService skeleton + preference merge

**Files:**
- Create: `backend/app/services/pipeline_service.py`
- Test: `backend/tests/integration/test_pipeline_service.py`

`PipelineService` is constructed with `(session, redis)`. `session` is any
`AsyncSession`; `redis` is any client with async `publish` (the ARQ pool or
`ctx['redis']`). It owns its own repositories built from that session.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_pipeline_service.py`:

```python
"""Integration tests for PipelineService — each phase against a real session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


async def _make_proposal(db, *, brief=None, pipeline_state=None):
    agency = await AgencyRepository(db).create(name="PS Agency", slug="ps-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id,
        client_id=client.id,
        project_name="PS Project",
        brief=brief or {},
        pipeline_state=pipeline_state or {"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return agency, client, proposal


def test_merge_preferences_into_config_overlays_user_prefs():
    merged = PipelineService._merge_preferences_into_config(
        {"narrative": {"letter_strategy": "vision"}},
        {"letter_strategy": "warm", "site_theme": "dark"},
    )
    assert merged["narrative"]["letter_strategy"] == "warm"
    assert merged["output"]["site_theme"] == "dark"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.pipeline_service`

- [ ] **Step 3: Write the skeleton**

Create `backend/app/services/pipeline_service.py`:

```python
"""The proposal-generation pipeline, extracted from ChatViewModel.

Each method runs one phase against the session it was constructed with, commits
its own writes, and publishes WebSocket events through Redis *after* the commit.
The worker process constructs this with a fresh per-job session; nothing here
touches a request-scoped session.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.services.ai.benchmark_agent import BenchmarkAgent
from app.services.ai.brief_analyzer import BriefAnalyzer
from app.services.ai.cost_model_builder import CostModelBuilder
from app.services.ai.narrative_generator import NarrativeGenerator
from app.services.ai.research_agent import ResearchAgent

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis
        self.proposal_repo = ProposalRepository(session)
        self.msg_repo = ChatMessageRepository(session)

    # ── WS helpers ───────────────────────────────────────────────────────────
    async def _emit(self, proposal_id, payload: dict) -> None:
        await publish(self.redis, str(proposal_id), payload)

    async def _emit_progress(self, proposal_id, agent: str, status: str, detail: str) -> None:
        await self._emit(proposal_id, {"type": "progress", "agent": agent, "status": status, "detail": detail})

    async def _emit_message(self, proposal_id, msg) -> None:
        await self._emit(proposal_id, {
            "type": "new_message",
            "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
        })

    async def _emit_phase_change(self, proposal_id, phase: str) -> None:
        await self._emit(proposal_id, {"type": "phase_change", "phase": phase})

    @staticmethod
    def _merge_preferences_into_config(template_config: dict | None, preferences: dict) -> dict:
        # MOVED VERBATIM from ChatViewModel._merge_preferences_into_config
        # (chat_viewmodel.py). Copy the existing static method body unchanged.
        ...
```

For Step 3, copy the **exact body** of `ChatViewModel._merge_preferences_into_config`
from `backend/app/viewmodels/chat_viewmodel.py` (the `@staticmethod` near the end
of the file) into the `_merge_preferences_into_config` here, replacing the `...`.
It is pure and needs no changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 1 test (`test_merge_preferences_into_config_overlays_user_prefs`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService skeleton with preference merge"
```

---

## Task 6: PipelineService.analyze_brief

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_pipeline_service.py`

`analyze_brief` is the extraction of `ChatViewModel._handle_brief_phase`. It runs
the `BriefAnalyzer`, and on a completed brief writes `proposal.brief`, creates the
`brief_summary` message, **commits**, then emits the message. On an incomplete
brief it just creates the follow-up text message, commits, emits.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_pipeline_service.py`:

```python
async def test_analyze_brief_persists_completed_brief_before_emitting(db, monkeypatch):
    from app.services.ai.brief_analyzer import BriefAnalysisResult, BriefAnalyzer

    _, _, proposal = await _make_proposal(db)
    pid = proposal.id

    async def fake_analyze(self, chat_history, current_brief):
        return BriefAnalysisResult(
            response_text="Confirm?", brief_complete=True,
            brief_data={"client": {"name": "Acme"}},
        )

    monkeypatch.setattr(BriefAnalyzer, "analyze", fake_analyze)
    emitted: list = []
    redis = AsyncMock()
    redis.publish.side_effect = lambda ch, raw: emitted.append(raw)

    svc = PipelineService(db, redis)
    await svc.analyze_brief(pid)

    # the brief is committed and visible from a fresh repo on a new session
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.brief == {"client": {"name": "Acme"}}

    assert emitted, "expected a WebSocket event to be published"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py::test_analyze_brief_persists_completed_brief_before_emitting -v`
Expected: FAIL — `AttributeError: 'PipelineService' object has no attribute 'analyze_brief'`

- [ ] **Step 3: Implement analyze_brief**

Add to `PipelineService` (in `pipeline_service.py`):

```python
    async def analyze_brief(self, proposal_id: UUID | str) -> None:
        """Brief-intake phase. Extracted from ChatViewModel._handle_brief_phase."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            logger.warning("analyze_brief: proposal %s not found", proposal_id)
            return

        all_messages = await self.msg_repo.list_by_proposal(proposal_id)
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in all_messages
            if m.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
            and m.message_type == MessageType.TEXT.value
        ]

        result = await BriefAnalyzer().analyze(chat_history=chat_history, current_brief=proposal.brief)

        msg_type = MessageType.TEXT.value
        extra_data: dict = {}
        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}
            await self.proposal_repo.update(proposal.id, brief=result.brief_data)

        assistant_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=msg_type,
            content=result.response_text,
            extra_data=extra_data,
            phase="brief",
        )
        await self.session.commit()          # commit BEFORE broadcasting
        await self._emit_message(proposal_id, assistant_msg)
        await self._emit(proposal_id, {"type": "typing", "typing": False})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService.analyze_brief"
```

---

## Task 7: PipelineService.run_research and run_benchmarks

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_pipeline_service.py`

Extraction of `ChatViewModel._run_research_and_benchmarks`, **split into two
methods**. `run_research` writes `proposal.research`, commits, emits progress.
`run_benchmarks` writes `proposal.benchmarks`, commits, creates the combined
`research_findings` message, commits, advances `pipeline_state` to
`cost_model_review`, commits, emits `phase_change`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_pipeline_service.py`:

```python
async def test_run_research_commits_research_before_emitting(db, monkeypatch):
    from app.services.ai.research_agent import ResearchAgent

    _, _, proposal = await _make_proposal(
        db, brief={"client": {"name": "Acme", "industry": "tech"}, "project": {"deliverables": []}}
    )
    pid = proposal.id

    async def fake_research(self, client_name, industry, queries=None, context_brief=None):
        return "## Research\nAcme is a tech company."

    monkeypatch.setattr(ResearchAgent, "research_client", fake_research)
    svc = PipelineService(db, AsyncMock())
    await svc.run_research(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.research == "## Research\nAcme is a tech company."


async def test_run_benchmarks_advances_pipeline_to_cost_model_review(db, monkeypatch):
    from app.services.ai.benchmark_agent import BenchmarkAgent

    _, _, proposal = await _make_proposal(
        db, brief={"client": {"name": "Acme"}, "project": {"deliverables": [{"category": "Logo"}]}}
    )
    pid = proposal.id

    async def fake_benchmarks(self, deliverables, region="India", queries=None):
        return "## Benchmarks\n₹X per logo."

    monkeypatch.setattr(BenchmarkAgent, "find_benchmarks", fake_benchmarks)
    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.benchmarks == "## Benchmarks\n₹X per logo."
        assert refetched.pipeline_state["current_phase"] == "cost_model_review"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -k "research or benchmarks" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'run_research'`

- [ ] **Step 3: Implement run_research and run_benchmarks**

Add to `PipelineService`. Reference: `chat_viewmodel.py` `_run_research_and_benchmarks` (the research/benchmark/template-config-loading logic). Build `template_config` by loading the proposal's `StrategyTemplate` (same logic as `_generate_narrative` uses). Implement:

```python
    async def _load_template_config(self, proposal) -> dict | None:
        if not proposal.template_id:
            return None
        from app.infrastructure.db.models.template import StrategyTemplate
        result = await self.session.execute(
            select(StrategyTemplate).where(StrategyTemplate.template_key == proposal.template_id)
        )
        tmpl = result.scalar_one_or_none()
        if tmpl and isinstance(tmpl.config, dict):
            return tmpl.config
        return None

    async def _load_context_brief(self, proposal) -> str | None:
        try:
            from app.infrastructure.db.models.client import Client
            from app.services.context_service import ContextService
            result = await self.session.execute(
                select(Client).where(Client.id == str(proposal.client_id))
            )
            client_row = result.scalar_one_or_none()
            if client_row and client_row.context_profile:
                client_name = proposal.brief.get("client", {}).get("name", "the client")
                return await ContextService().generate_context_brief(
                    client_name, client_row.context_profile
                )
        except Exception:  # noqa: BLE001 — context is best-effort
            logger.exception("context brief load failed")
        return None

    async def run_research(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        brief = proposal.brief
        client_name = brief.get("client", {}).get("name", "the client")
        industry = brief.get("client", {}).get("industry")
        template_config = await self._load_template_config(proposal)
        context_brief = await self._load_context_brief(proposal)
        research_queries = (
            (template_config or {}).get("research", {}).get("client_queries")
        )

        await self._emit_progress(proposal_id, "research", "searching", f"Researching {client_name}...")
        research_md = await ResearchAgent().research_client(
            client_name, industry, research_queries, context_brief=context_brief
        )
        await self.proposal_repo.update(proposal.id, research=research_md)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_progress(proposal_id, "research", "complete", "Client research done")

    async def run_benchmarks(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        brief = proposal.brief
        deliverables = brief.get("project", {}).get("deliverables", [])
        template_config = await self._load_template_config(proposal)
        benchmark_queries = (
            (template_config or {}).get("research", {}).get("benchmark_queries")
        )

        await self._emit_progress(proposal_id, "benchmarks", "searching", "Finding pricing benchmarks...")
        benchmarks_md = await BenchmarkAgent().find_benchmarks(deliverables, "India", benchmark_queries)
        await self.proposal_repo.update(proposal.id, benchmarks=benchmarks_md)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_progress(proposal_id, "benchmarks", "complete", "Pricing benchmarks done")

        # combined research + benchmarks findings message
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        summary = (
            f"**Research and benchmarking complete.**\n\n---\n\n"
            f"{proposal.research}\n\n---\n\n{benchmarks_md}"
        )
        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.RESEARCH_FINDINGS.value,
            content=summary,
            extra_data={"has_research": True, "has_benchmarks": True},
            phase="research",
        )
        # advance pipeline
        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["research"]
        pipeline["current_phase"] = "cost_model_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_message(proposal_id, msg)
        await self._emit_phase_change(proposal_id, "cost_model_review")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService.run_research and run_benchmarks"
```

---

## Task 8: PipelineService.build_cost_model

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_pipeline_service.py`

Extraction of `ChatViewModel._build_cost_model`. Builds the cost model, writes
`proposal.cost_model`, **commits**, creates the `cost_model` message (with the
human-readable table from the existing method), commits, emits.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_pipeline_service.py`:

```python
async def test_build_cost_model_commits_model_and_creates_message(db):
    from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository

    agency, _, proposal = await _make_proposal(
        db, brief={"project": {"deliverables": [{"category": "logo design", "details": "mark", "quantity": 1}]}}
    )
    await RateCardRepository(db).create(
        agency_id=agency.id, version="v1", is_active=True,
        offerings={"branding": {"packages": {"logo": {"base": 100000, "description": "logo design"}}}},
        hourly_rates={"design": 5000}, multipliers={},
    )
    await db.commit()
    pid = proposal.id

    svc = PipelineService(db, AsyncMock())
    await svc.build_cost_model(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.cost_model.get("line_items")
        msgs = await ChatMessageRepository(fresh).list_by_proposal(pid)
        assert any(m.message_type == "cost_model" for m in msgs)


# add at top of file:
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py::test_build_cost_model_commits_model_and_creates_message -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_cost_model'`

- [ ] **Step 3: Implement build_cost_model**

Add to `PipelineService`. Copy the cost-model-summary formatting (the `lines = [...]` block building the markdown table) **verbatim** from `chat_viewmodel.py:_build_cost_model`:

```python
    async def build_cost_model(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        template_config = await self._load_template_config(proposal)

        await self._emit_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        model = await CostModelBuilder().build(
            brief=proposal.brief,
            db=self.session,
            agency_id=str(proposal.agency_id),
            benchmarks_md=proposal.benchmarks,
            template_config=template_config,
        )
        cost_dict = CostModelBuilder.model_to_dict(model)
        await self.proposal_repo.update(proposal.id, cost_model=cost_dict)
        await self.session.commit()                       # commit BEFORE broadcast

        # human-readable summary — COPY the `lines = [...]` block verbatim from
        # ChatViewModel._build_cost_model in chat_viewmodel.py
        lines = ["**Cost Model — Review & Approve**\n"]
        # ... (verbatim copy) ...
        content = "\n".join(lines)

        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.COST_MODEL.value,
            content=content,
            extra_data={"cost_model": cost_dict, "requires_approval": True, "gate_type": "cost_model"},
            phase="cost_model_review",
        )
        await self.session.commit()
        await self._emit_progress(proposal_id, "cost_model", "complete", "Cost model ready for review")
        await self._emit_message(proposal_id, msg)
```

Replace the `# ... (verbatim copy) ...` with the exact `lines.append(...)` block
from `chat_viewmodel.py:_build_cost_model` (lines that build the deliverable
table, subtotal, discount, GST, grand total, multipliers).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService.build_cost_model"
```

---

## Task 9: PipelineService.generate_narrative

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_pipeline_service.py`

Extraction of `ChatViewModel._generate_narrative`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_pipeline_service.py`:

```python
async def test_generate_narrative_commits_sections_and_advances_pipeline(db, monkeypatch):
    from app.services.ai.narrative_generator import NarrativeGenerator

    agency, _, proposal = await _make_proposal(
        db,
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "narrative_generation", "phases_completed": ["research"]},
    )
    pid = proposal.id

    class _Narr:
        covering_letter = "Dear Acme,"
        covering_letter_alt = "Hi Acme,"
        executive_summary = "Summary."
        scope_sections = [{"title": "Logo", "body": "..."}]
        cost_rationale = "Because."
        terms = "Net 30."
        letter_strategy_primary = "confident"
        letter_strategy_alt = "warm"

    async def fake_generate_all(self, **kwargs):
        return _Narr()

    monkeypatch.setattr(NarrativeGenerator, "generate_all", fake_generate_all)
    svc = PipelineService(db, AsyncMock())
    await svc.generate_narrative(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.covering_letter == "Dear Acme,"
        assert refetched.executive_summary == "Summary."
        assert refetched.pipeline_state["current_phase"] == "narrative_review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py::test_generate_narrative_commits_sections_and_advances_pipeline -v`
Expected: FAIL — `AttributeError: ... has no attribute 'generate_narrative'`

- [ ] **Step 3: Implement generate_narrative**

Add `generate_narrative` to `PipelineService` as a faithful extraction of
`ChatViewModel._generate_narrative` (`chat_viewmodel.py`), with these mechanical
changes:
- Signature: `async def generate_narrative(self, proposal_id: UUID | str) -> None:`
  — load `proposal = await self.proposal_repo.get_by_id(proposal_id)` at the top;
  return early if `None`.
- `self._db` → `self.session` everywhere.
- `self.proposal_repo` → `self.proposal_repo` (already on `self`).
- Use `self._merge_preferences_into_config(...)` (now a static method on this class).
- Use `self._load_template_config(proposal)` instead of the inline template load.
- After `await self.proposal_repo.update(proposal.id, covering_letter=..., ...)`
  for the narrative sections **and** after the `pipeline_state` update, call
  `await self.session.commit()` **before** any emit.
- Replace the two `ws_manager.broadcast(...)` calls and `_broadcast_progress(...)`
  calls with `await self._emit_progress(...)` / `await self._emit_phase_change(...)`.
- Replace the final `return await self.msg_repo.create(...)` with: create the
  message, `await self.session.commit()`, then `await self._emit_message(proposal_id, msg)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService.generate_narrative"
```

---

## Task 10: PipelineService.generate_outputs

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/integration/test_pipeline_service.py`

Extraction of `ChatViewModel._generate_outputs`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_pipeline_service.py`:

```python
async def test_generate_outputs_commits_status_and_advances_to_complete(db, tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))  # keep file writes in tmp

    agency, _, proposal = await _make_proposal(
        db,
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "output_generation", "phases_completed": ["research", "narrative_review"]},
    )
    # give the proposal narrative content so generation has something to render
    await ProposalRepository(db).update(
        proposal.id, covering_letter="Dear Acme,", executive_summary="Summary.",
        scope_sections=[], terms="Net 30.",
    )
    await db.commit()
    pid = proposal.id

    svc = PipelineService(db, AsyncMock())
    await svc.generate_outputs(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.pipeline_state["current_phase"] == "complete"
        assert refetched.status == "review"
```

Note: `OUTPUT_DIR` is a computed Pydantic field; if `monkeypatch.setenv` does not
override it (it is `@computed_field`), instead `monkeypatch.setattr` the
`get_settings()` result's behavior, or `monkeypatch.setattr(PipelineService,
...)`. Simplest robust approach: in Step 3, have `generate_outputs` resolve the
output dir via `get_settings().OUTPUT_DIR` and in the test
`monkeypatch.setattr("app.services.pipeline_service.get_settings", lambda: <a
settings stub with OUTPUT_DIR=str(tmp_path)>)`. Use whichever the engineer
confirms works against the real `Settings` definition in `config.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py::test_generate_outputs_commits_status_and_advances_to_complete -v`
Expected: FAIL — `AttributeError: ... has no attribute 'generate_outputs'`

- [ ] **Step 3: Implement generate_outputs**

Add `generate_outputs` to `PipelineService` as a faithful extraction of
`ChatViewModel._generate_outputs` (`chat_viewmodel.py`), with these mechanical
changes:
- Signature: `async def generate_outputs(self, proposal_id: UUID | str) -> None:`
  — load the proposal at the top; return early if `None`.
- `self._db` → `self.session`; `self.proposal_repo` already on `self`.
- The narrative `extra_data` fallback block (the `if narr_msgs and not
  prop_data["covering_letter"]:` branch) **can be deleted** — with per-phase
  commits the proposal fields are always populated. Keep it for now if unsure;
  removing it is the point of the fix but is not required for tests to pass.
- After `await self.proposal_repo.update(proposal.id, pipeline_state=pipeline,
  status="review")`, call `await self.session.commit()` **before** any emit.
- Replace `_broadcast_progress` / `ws_manager.broadcast` with `self._emit_progress`
  / `self._emit_phase_change`.
- Replace the final `return await self.msg_repo.create(...)` with: create message,
  `await self.session.commit()`, `await self._emit_message(proposal_id, msg)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_service.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_pipeline_service.py
git commit -m "feat: PipelineService.generate_outputs"
```

---

## Task 11: ARQ worker tasks

**Files:**
- Create: `backend/app/workers/pipeline.py`
- Test: `backend/tests/integration/test_pipeline_worker.py`

Each ARQ task: mark `job_status` running → run the `PipelineService` phase →
mark `job_status` complete → enqueue the next phase → on exception, after
`ARQ_MAX_TRIES` mark `job_status` failed + emit error, otherwise re-raise to retry.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_pipeline_worker.py`:

```python
"""Tests for the ARQ pipeline task functions."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.workers import pipeline as worker


async def _make_proposal(db):
    agency = await AgencyRepository(db).create(name="W Agency", slug="w-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="W Project",
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    await db.commit()
    return proposal


def _ctx(job_try=1):
    return {"redis": AsyncMock(), "job_try": job_try}


async def test_run_research_task_sets_job_status_and_enqueues_next(db, monkeypatch):
    from app.services.ai.research_agent import ResearchAgent

    proposal = await _make_proposal(db)
    pid = str(proposal.id)

    async def fake_research(self, *a, **k):
        return "## Research"

    monkeypatch.setattr(ResearchAgent, "research_client", fake_research)
    ctx = _ctx()
    await worker.run_research(ctx, pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.pipeline_state["job_status"]["state"] == "complete"
    ctx["redis"].enqueue_job.assert_awaited()  # chained run_benchmarks
    assert ctx["redis"].enqueue_job.await_args.args[0] == "run_benchmarks"


async def test_task_marks_failed_after_max_tries(db, monkeypatch):
    from app.services.ai.research_agent import ResearchAgent

    proposal = await _make_proposal(db)
    pid = str(proposal.id)

    async def boom(self, *a, **k):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(ResearchAgent, "research_client", boom)
    ctx = _ctx(job_try=worker.ARQ_MAX_TRIES)  # last attempt
    await worker.run_research(ctx, pid)  # must NOT raise on the final try

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        assert refetched.pipeline_state["job_status"]["state"] == "failed"
        assert "LLM down" in refetched.pipeline_state["job_status"]["error"]


async def test_task_reraises_to_retry_before_max_tries(db, monkeypatch):
    from app.services.ai.research_agent import ResearchAgent

    proposal = await _make_proposal(db)
    pid = str(proposal.id)

    async def boom(self, *a, **k):
        raise RuntimeError("transient")

    monkeypatch.setattr(ResearchAgent, "research_client", boom)
    ctx = _ctx(job_try=1)  # not the last attempt
    with pytest.raises(RuntimeError, match="transient"):
        await worker.run_research(ctx, pid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: app.workers.pipeline`

- [ ] **Step 3: Write the worker module**

Create `backend/app/workers/pipeline.py`:

```python
"""ARQ pipeline tasks — one durable job per proposal-pipeline phase.

Each task opens its own AsyncSession, runs a PipelineService phase (which commits
before it broadcasts), records job_status on the proposal, and chains the next
phase. Run the worker process with: ``arq app.workers.pipeline.WorkerSettings``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.infrastructure.queue.redis import get_redis_settings
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

ARQ_MAX_TRIES = get_settings().ARQ_MAX_TRIES

# phase -> the job that runs automatically after it (chaining within a gate)
_NEXT_PHASE = {
    "run_research": "run_benchmarks",
    "run_benchmarks": "build_cost_model",
}


async def _set_job_status(session, proposal_id, phase, state, error=None) -> None:
    repo = ProposalRepository(session)
    proposal = await repo.get_by_id(proposal_id)
    if proposal is None:
        return
    pipeline = proposal.pipeline_state.copy()
    pipeline["job_status"] = {
        "phase": phase,
        "state": state,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await repo.update(proposal_id, pipeline_state=pipeline)
    await session.commit()


async def _run_phase(ctx: dict, phase: str, proposal_id: str) -> None:
    """Shared task body: status bookkeeping + retry-to-failed handling."""
    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "running")

    try:
        async with async_session_factory() as session:
            svc = PipelineService(session, ctx["redis"])
            await getattr(svc, phase)(proposal_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline phase %s failed for %s", phase, proposal_id)
        if ctx["job_try"] >= ARQ_MAX_TRIES:
            async with async_session_factory() as session:
                await _set_job_status(session, proposal_id, phase, "failed", str(exc))
            await publish(ctx["redis"], proposal_id, {
                "type": "pipeline_error", "phase": phase, "error": str(exc),
            })
            return  # swallow on the final try — job is "done" (failed)
        raise  # let ARQ retry

    async with async_session_factory() as session:
        await _set_job_status(session, proposal_id, phase, "complete")

    next_phase = _NEXT_PHASE.get(phase)
    if next_phase:
        await ctx["redis"].enqueue_job(
            next_phase, proposal_id, _job_id=f"{proposal_id}:{next_phase}"
        )


async def analyze_brief(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "analyze_brief", proposal_id)


async def run_research(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_research", proposal_id)


async def run_benchmarks(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "run_benchmarks", proposal_id)


async def build_cost_model(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "build_cost_model", proposal_id)


async def generate_narrative(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_narrative", proposal_id)


async def generate_outputs(ctx: dict, proposal_id: str) -> None:
    await _run_phase(ctx, "generate_outputs", proposal_id)


class WorkerSettings:
    functions = [
        analyze_brief, run_research, run_benchmarks,
        build_cost_model, generate_narrative, generate_outputs,
    ]
    redis_settings = get_redis_settings()
    max_tries = ARQ_MAX_TRIES
```

Note: `_run_phase` calls `getattr(svc, phase)` — the phase name strings
(`run_research`, `build_cost_model`, …) must exactly match `PipelineService`
method names. They do, by construction.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_worker.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/pipeline.py backend/tests/integration/test_pipeline_worker.py
git commit -m "feat: ARQ pipeline worker tasks with job_status and retry-to-failed"
```

---

## Task 12: Rewrite ChatViewModel to enqueue jobs

**Files:**
- Modify: `backend/app/viewmodels/chat_viewmodel.py`

Remove the pipeline methods (now in `PipelineService`) and make `send_message` /
`approve_gate` validate → update `pipeline_state` → create an ack message →
enqueue the first job → return.

- [ ] **Step 1: Delete the extracted methods**

In `backend/app/viewmodels/chat_viewmodel.py`, **delete** these methods entirely
(their logic now lives in `PipelineService`):
`_handle_brief_phase`, `_run_research_and_benchmarks`, `_broadcast_progress`,
`_build_cost_model`, `_generate_narrative`, `_generate_outputs`,
`_merge_preferences_into_config`. Keep `_handle_template_confirm`, `_echo_response`,
`_broadcast_msg`, `get_messages`.

- [ ] **Step 2: Add an enqueue helper**

Add to `ChatViewModel`:

```python
    async def _enqueue(self, job_name: str, proposal_id) -> None:
        pool = self._request.app.state.arq_pool
        await pool.enqueue_job(
            job_name, str(proposal_id), _job_id=f"{proposal_id}:{job_name}"
        )

    async def _set_job_queued(self, proposal, phase: str) -> dict:
        pipeline = proposal.pipeline_state.copy()
        pipeline["job_status"] = {"phase": phase, "state": "queued", "error": None}
        return pipeline
```

- [ ] **Step 3: Rewrite send_message**

Replace `send_message` so the brief phase enqueues `analyze_brief` instead of
running `_handle_brief_phase` inline:

```python
    async def send_message(
        self, proposal_id: UUID, agency_id: UUID, content: str,
    ) -> list[ChatMessage] | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        current_phase = proposal.pipeline_state.get("current_phase", "brief")

        user_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.USER.value,
            message_type=MessageType.TEXT.value,
            content=content,
            phase=current_phase,
        )
        await self._broadcast_msg(proposal_id, user_msg)

        if current_phase == "brief":
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})
            pipeline = await self._set_job_queued(proposal, "analyze_brief")
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
            await self._enqueue("analyze_brief", proposal_id)
            self.status_code = 201
            return [user_msg]

        # non-brief phases: unchanged echo placeholder
        assistant_msg = await self._echo_response(proposal_id, content, current_phase)
        await self._broadcast_msg(proposal_id, assistant_msg)
        self.status_code = 201
        return [user_msg, assistant_msg]
```

- [ ] **Step 4: Rewrite approve_gate**

Replace `approve_gate`. The `brief` gate stays synchronous (template matching is
instant). The `template`, `cost_model`, `narrative` gates update `pipeline_state`,
create an ack message, and enqueue the first phase job:

```python
    async def approve_gate(
        self, proposal_id: UUID, agency_id: UUID, gate_id: str, gate_data: dict | None = None,
    ) -> ChatMessage | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        pipeline = proposal.pipeline_state.copy()

        if gate_id == "brief":
            # synchronous — template matching has no LLM call
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["brief"]
            pipeline["current_phase"] = "template_confirm"
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
            msg = await self.msg_repo.create(
                proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Brief approved. Let me find the best template for this project...",
                phase="template_confirm",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "template_confirm"})
            template_msg = await self._handle_template_confirm(proposal, proposal_id, "")
            await self._broadcast_msg(proposal_id, template_msg)
            return msg

        gate_map = {
            "template": ("research", "run_research",
                         "Template confirmed. Starting client research and market benchmarking..."),
            "cost_model": ("narrative_generation", "generate_narrative",
                           "Cost model approved. Writing the proposal narrative..."),
            "narrative": ("output_generation", "generate_outputs",
                          "Narrative approved. Generating DOCX, print-ready PDF, and email drafts..."),
        }
        if gate_id not in gate_map:
            self.error = f"Unknown gate: {gate_id}"
            self.status_code = 400
            return None

        next_phase, job_name, ack_text = gate_map[gate_id]

        if gate_id == "template":
            template_key = (gate_data or {}).get("template_key")
            if template_key:
                await self.proposal_repo.update(proposal.id, template_id=template_key)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["template_confirm"]
        elif gate_id == "cost_model":
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["cost_model_review"]
        elif gate_id == "narrative":
            selected_letter = (gate_data or {}).get("selected_letter", "primary")
            if selected_letter == "alt" and proposal.covering_letter_alt:
                await self.proposal_repo.update(proposal.id, covering_letter=proposal.covering_letter_alt)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["narrative_review"]

        pipeline["current_phase"] = next_phase
        pipeline["job_status"] = {"phase": job_name, "state": "queued", "error": None}
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

        msg = await self.msg_repo.create(
            proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value, content=ack_text, phase=next_phase,
        )
        await self._broadcast_msg(proposal_id, msg)
        await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": next_phase})
        await self._enqueue(job_name, proposal_id)
        return msg
```

- [ ] **Step 5: Verify it compiles and imports**

Run: `cd backend && .venv/bin/python -m py_compile app/viewmodels/chat_viewmodel.py && .venv/bin/python -c "from app.viewmodels.chat_viewmodel import ChatViewModel; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/viewmodels/chat_viewmodel.py
git commit -m "refactor: ChatViewModel enqueues pipeline jobs instead of running them inline"
```

---

## Task 13: chat.py — send_message response + retry endpoint

**Files:**
- Modify: `backend/app/views/v1/chat.py`

- [ ] **Step 1: Update send_message route**

`vm.send_message` now returns `list[ChatMessage]` (1 or 2 items). The route's
`response_model` is already `list[ChatMessageResponse]`. Replace the route body so
it validates each returned message:

```python
@router.post("/{proposal_id}/send", response_model=list[ChatMessageResponse], status_code=status.HTTP_201_CREATED)
async def send_message(
    proposal_id: UUID,
    body: SendMessageRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    result = await vm.send_message(proposal_id, agency_id, body.content)
    if result is None:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return [ChatMessageResponse.model_validate(m) for m in result]
```

- [ ] **Step 2: Add the retry endpoint**

Add after `approve_gate`:

```python
@router.post("/{proposal_id}/retry", response_model=dict)
async def retry_failed_phase(
    proposal_id: UUID,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    """Re-enqueue the phase recorded as failed in pipeline_state.job_status."""
    proposal = await vm.proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    job_status = (proposal.pipeline_state or {}).get("job_status") or {}
    if job_status.get("state") != "failed":
        raise HTTPException(status_code=400, detail="No failed phase to retry")
    phase = job_status["phase"]
    pipeline = proposal.pipeline_state.copy()
    pipeline["job_status"] = {"phase": phase, "state": "queued", "error": None}
    await vm.proposal_repo.update(proposal_id, pipeline_state=pipeline)
    await vm._enqueue(phase, proposal_id)
    return {"phase": phase, "state": "queued"}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd backend && .venv/bin/python -m py_compile app/views/v1/chat.py && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"`
Expected: prints `routes: 62` (one new route).

- [ ] **Step 4: Commit**

```bash
git add backend/app/views/v1/chat.py
git commit -m "feat: send_message returns user message only; add retry endpoint"
```

---

## Task 14: Test fixtures — mock ARQ pool + events spy

**Files:**
- Modify: `backend/tests/conftest.py`

The ASGI test client does not run `lifespan`, so `app.state.arq_pool` is unset.
Add a fixture that installs a mock pool and an `events.publish` spy.

- [ ] **Step 1: Add the fixtures**

In `backend/tests/conftest.py`, add these imports near the top (after the existing
`app` imports):

```python
from unittest.mock import AsyncMock  # noqa: E402
```

Add these fixtures (after `seeded_templates`):

```python
@pytest.fixture
def arq_pool(monkeypatch):
    """Install a mock ARQ pool on app.state so enqueue calls are captured."""
    pool = AsyncMock()
    app.state.arq_pool = pool
    yield pool
    if hasattr(app.state, "arq_pool"):
        delattr(app.state, "arq_pool")


@pytest.fixture(autouse=True)
def ws_publish_spy(monkeypatch):
    """Stub events.publish so pipeline code never needs a real Redis in tests."""
    published: list[tuple[str, dict]] = []

    async def _spy(redis, proposal_id, payload):  # noqa: ANN001
        published.append((str(proposal_id), payload))

    monkeypatch.setattr("app.infrastructure.queue.events.publish", _spy)
    # PipelineService imports `publish` by name — patch that binding too
    monkeypatch.setattr("app.services.pipeline_service.publish", _spy, raising=False)
    return published
```

- [ ] **Step 2: Verify conftest still loads**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_health.py -v`
Expected: PASS — 2 tests (proves conftest imports cleanly).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: mock ARQ pool and events.publish spy fixtures"
```

---

## Task 15: Rewrite test_persistence_bug.py as a real test

**Files:**
- Modify: `backend/tests/integration/test_persistence_bug.py`

- [ ] **Step 1: Replace the file**

Replace `backend/tests/integration/test_persistence_bug.py` entirely:

```python
"""Regression test for the proposal-field persistence bug.

Previously the whole pipeline ran in one request transaction committed only at
request end, so a phase's writes were not visible to a concurrent reader until
the entire request finished. Now each phase commits in its own session before it
broadcasts — proven here by reading the written field from a *separate* session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


async def test_phase_commits_before_it_would_broadcast(db, monkeypatch):
    from app.services.ai.research_agent import ResearchAgent

    agency = await AgencyRepository(db).create(name="P Agency", slug="p-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P",
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    await db.commit()
    pid = proposal.id

    research_text = "## Research\nCommitted before broadcast."

    async def fake_research(self, *a, **k):
        return research_text

    monkeypatch.setattr(ResearchAgent, "research_client", fake_research)

    # capture WS emits and assert the DB write is already visible when one fires
    seen_committed_at_emit: list[bool] = []

    async def _emit_spy(redis, proposal_id, payload):  # noqa: ANN001
        async with async_session_factory() as observer:
            row = await ProposalRepository(observer).get_by_id(proposal_id)
            seen_committed_at_emit.append(row is not None and row.research == research_text)

    monkeypatch.setattr("app.services.pipeline_service.publish", _emit_spy, raising=False)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(pid)

    # at least one broadcast happened, and every broadcast saw the committed write
    assert seen_committed_at_emit, "run_research should emit at least one WS event"
    assert all(seen_committed_at_emit), "every broadcast must follow the phase commit"
```

- [ ] **Step 2: Run it**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_persistence_bug.py -v`
Expected: PASS — 1 test (no longer skipped).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_persistence_bug.py
git commit -m "test: persistence bug regression test now passes (no longer skipped)"
```

---

## Task 16: Update test_chat_api.py for the enqueue model

**Files:**
- Modify: `backend/tests/integration/test_chat_api.py`

`approve_gate` and the brief-phase `send_message` no longer run the pipeline
inline — they enqueue. Update the affected tests to require the `arq_pool` fixture
and assert the enqueue + ack message instead of pipeline output.

- [ ] **Step 1: Update the brief-phase send_message test**

Replace `test_send_message_ai_path_completes_brief` with:

```python
async def test_send_message_brief_phase_enqueues_analyze_brief(client, registered, arq_pool):
    """In the brief phase, send_message persists the user message and enqueues
    the analyze_brief job — it does not run the analyzer inline."""
    p = await _make_proposal(client, registered.headers)
    resp = await client.post(
        f"{API}/chat/{p['id']}/send",
        headers=registered.headers,
        json={"content": "Acme needs a rebrand"},
    )
    assert resp.status_code == 201
    msgs = resp.json()
    assert len(msgs) == 1  # user message only; assistant reply arrives via WS
    assert msgs[0]["role"] == "user"

    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "analyze_brief"
```

- [ ] **Step 2: Update the approve-brief-gate test**

`test_approve_brief_gate_advances_pipeline` is unchanged in behavior (the brief
gate stays synchronous) — it should still pass. Verify it does in Step 4.

- [ ] **Step 3: Replace the approve-template-gate coverage**

Replace `test_approve_unknown_gate_400` is unchanged. Add a new test for the
template gate enqueue:

```python
async def test_approve_template_gate_enqueues_research(client, registered, arq_pool, seeded_templates):
    p = await _make_proposal(client, registered.headers)
    # advance the proposal to template_confirm via the brief gate
    await client.post(f"{API}/chat/{p['id']}/approve/brief", headers=registered.headers, json={"data": {}})

    resp = await client.post(
        f"{API}/chat/{p['id']}/approve/template",
        headers=registered.headers,
        json={"data": {"template_key": "brand_identity"}},
    )
    assert resp.status_code == 200
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"

    prop = await client.get(f"{API}/proposals/{p['id']}", headers=registered.headers)
    pipeline = prop.json()["pipeline_state"]
    assert pipeline["current_phase"] == "research"
    assert pipeline["job_status"]["state"] == "queued"
```

- [ ] **Step 4: Run the chat API tests**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_api.py -v`
Expected: PASS — all tests. (`test_patch_cost_model_item_recalculates_totals` and the
`get_messages` tests are unaffected.)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_chat_api.py
git commit -m "test: chat API tests assert job enqueue instead of inline pipeline"
```

---

## Task 17: Full backend suite green

**Files:** none (verification task)

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all tests PASS, **0 skipped** (the persistence-bug test now runs). If
any test fails, fix it before continuing — common causes:
- A test still referencing a deleted `ChatViewModel` method → move the assertion
  to `test_pipeline_service.py`.
- A test that relied on `approve_gate` running the pipeline inline → add the
  `arq_pool` fixture and assert the enqueue.

- [ ] **Step 2: Verify the app still boots**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"`
Expected: `routes: 62`

- [ ] **Step 3: Commit (only if fixes were needed)**

```bash
git add backend/tests
git commit -m "test: fix fallout from background-worker pipeline refactor"
```

---

## Task 18: Frontend — useSendMessage returns user message only

**Files:**
- Modify: `frontend/src/api/proposals.ts`
- Modify: `frontend/src/pages/proposals/builder.tsx`
- Modify: `frontend/src/api/__tests__/proposals.test.ts`

- [ ] **Step 1: Update the test**

In `frontend/src/api/__tests__/proposals.test.ts`, the `useSendMessage` test
already only asserts the request body — no change needed there. Add a comment
clarifying the response shape, and verify the existing test still passes in Step 4.

- [ ] **Step 2: Check builder.tsx for response usage**

Open `frontend/src/pages/proposals/builder.tsx`. Find where `useSendMessage`'s
result is consumed (the `mutate`/`mutateAsync` `onSuccess` or the awaited result).
If it reads `result[1]` (the old assistant message), change it to: optimistically
add only `result[0]` (the user message) to the chat store — the assistant reply
arrives via the WebSocket `new_message` event, which the store already dedupes.
If it already only uses `result[0]` or relies entirely on WS, no change is needed.

```typescript
// before (if present): adds both user + assistant from the response
// after: add only the user message; assistant arrives over the WS channel
const sent = await sendMessage.mutateAsync({ proposalId, content })
sent.forEach((m) => useChatStore.getState().addMessage(m))
```

`sent` is now a 1-element array, so `forEach` is correct and forward-compatible.

- [ ] **Step 3: No type change needed**

`useSendMessage` already types the response as `ChatMessage[]` — a 1-element array
satisfies it. No change to `proposals.ts` types.

- [ ] **Step 4: Run the frontend suite**

Run: `cd frontend && pnpm test`
Expected: all 87+ tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/proposals/builder.tsx frontend/src/api/__tests__/proposals.test.ts
git commit -m "feat: builder consumes user message from send response, assistant via WS"
```

---

## Task 19: Deployment config — Redis + worker process

**Files:**
- Modify: `docker-compose.yml`
- Modify: `fly.toml`

- [ ] **Step 1: Add Redis + worker to docker-compose**

In `docker-compose.yml`, add a `redis` service and a `worker` service. The worker
reuses the app image with a different command:

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  worker:
    build: .
    command: arq app.workers.pipeline.WorkerSettings
    working_dir: /app/backend
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis
```

Also add `REDIS_URL=redis://redis:6379/0` and `depends_on: [redis]` to the
existing API service. (Match the exact key names/structure already in the file.)

- [ ] **Step 2: Add the worker process to fly.toml**

In `fly.toml`, add a `[processes]` block and move the implicit web command into it:

```toml
[processes]
  app = "uvicorn app.main:app --host 0.0.0.0 --port 8080"
  worker = "arq app.workers.pipeline.WorkerSettings"
```

Add a comment near `[env]` noting `REDIS_URL` must be set (Upstash Redis in prod)
for both processes.

- [ ] **Step 3: Verify compose config is valid**

Run: `docker compose config -q`
Expected: no output, exit 0 (config parses).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml fly.toml
git commit -m "chore: add Redis and ARQ worker process to docker-compose and fly.toml"
```

---

## Task 20: Final verification

**Files:** none (verification task)

- [ ] **Step 1: Backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all PASS, 0 skipped.

- [ ] **Step 2: Frontend suite + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: all tests PASS; `tsc -b && vite build` succeeds.

- [ ] **Step 3: End-to-end smoke (requires Redis)**

```bash
# terminal 1
docker run --rm -p 6379:6379 redis:7-alpine
# terminal 2
cd backend && .venv/bin/arq app.workers.pipeline.WorkerSettings
# terminal 3
cd backend && .venv/bin/uvicorn app.main:app --port 8000
# terminal 4 — register, create client+proposal, send a brief message,
# observe the worker log run analyze_brief and the proposal.brief get committed.
```
Expected: the worker process picks up `analyze_brief`; `GET /proposals/{id}` shows
the committed brief; no errors in either process log.

- [ ] **Step 4: Update memory**

Update `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md`:
move the proposal-persistence bug out of "Known Issues" into a "Resolved" note
referencing the ARQ background-worker pipeline.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "docs: mark proposal-persistence bug resolved via background workers"
```

---

## Self-Review

**Spec coverage:**
- Per-phase durable jobs → Tasks 5–11. ✅
- Commit-before-broadcast → enforced in every `PipelineService` method (Tasks 6–10) and proven by Task 15. ✅
- ARQ + per-phase + Redis-required → Tasks 1, 11, 19. ✅
- WS pub/sub bridge → Tasks 3, 4. ✅
- `job_status` tracking + retry-to-failed + retry endpoint → Tasks 11, 12, 13. ✅
- `PipelineService` extraction / `ChatViewModel` slim-down → Tasks 5–12. ✅
- Frontend touchpoint → Task 18. ✅
- Tests without live Redis → Tasks 14–17 (mock pool, `publish` spy, direct phase calls). ✅
- `test_persistence_bug.py` real test → Task 15. ✅
- docker-compose / fly.toml → Task 19. ✅

**Placeholder scan:** The `# verbatim copy` instructions in Tasks 5, 8, 9, 10 are
precise mechanical extractions (named source method, named transformations), not
vague placeholders — the engineer has the source file open. The `OUTPUT_DIR` note
in Task 10 Step 1 flags a concrete decision point with two named resolutions.

**Type consistency:** `PipelineService` method names (`analyze_brief`,
`run_research`, `run_benchmarks`, `build_cost_model`, `generate_narrative`,
`generate_outputs`) are used identically in Task 11's `getattr(svc, phase)` and
`_NEXT_PHASE`, in Task 12's `gate_map`, and in the worker task names. The
`pipeline_state.job_status` shape (`phase`/`state`/`error`/`updated_at`) is
written consistently in Tasks 11 and 12 and read in Task 13.
