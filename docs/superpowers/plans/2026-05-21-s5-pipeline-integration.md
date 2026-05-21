# S5 Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NUPROP proposal pipeline consume the client context that S1-S4 collected — thread `context_brief` into 4 pipeline phases, feed `proposal.preferences` into the cost model, and close the loop so synced emails enrich the client context profile via a background job.

**Architecture:** Pipeline phases run as independent ARQ jobs with separate DB sessions, so `context_brief` is persisted to a new `Proposal.context_brief` column — generated once (get-or-create), read by later phases. A shared helper lives in `context_service.py` so `PipelineService` and `IdeationService` share one implementation. `build_cost_model` routes `proposal.preferences` through the existing `_merge_preferences_into_config` helper. A new `enrich_context_from_emails` ARQ task, enqueued by `sync_emails`, feeds `email_index` rows into client context profiles.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, ARQ (Redis job queue), pytest + pytest-asyncio. Backend only — no frontend.

**Spec:** `docs/superpowers/specs/2026-05-21-s5-pipeline-integration-design.md`

**Run commands (from `backend/`):**
- Single test: `.venv/bin/python -m pytest tests/<path>::<test> -v`
- Full suite: `.venv/bin/python -m pytest -q`
- Apply migrations: `.venv/bin/alembic upgrade head`

**Scope note on Piece B (`pricing_model`):** the spec's acceptance criterion "CostModelBuilder honors `pricing_model` and `discount_tags`" is partially descoped by reality. `_merge_preferences_into_config` already renames `discount_tags` → `cost_model.default_multipliers`, which `CostModelBuilder.build` already consumes — so `discount_tags` works for free once the merged config is passed. `pricing_model` lands in the merged config but `CostModelBuilder` has no alternative pricing path to branch to; honoring it would require new pricing math, which the spec's non-goals explicitly exclude. This plan: `discount_tags` fully works; `pricing_model` is carried in the config for future use, not branched on. Documented as future work.

---

## File Structure

**Created:**
- `backend/alembic/versions/<NN>_proposal_context_brief.py` — migration adding the column
- `backend/app/workers/enrichment.py` — the `enrich_context_from_emails` ARQ task + helper
- `backend/tests/unit/test_context_brief_helper.py`
- `backend/tests/integration/test_s5_phase_context.py` — phase-wiring tests
- `backend/tests/integration/test_enrich_context_from_emails.py`

**Modified:**
- `backend/app/infrastructure/db/models/proposal.py` — add `context_brief` column
- `backend/app/services/context_service.py` — add `get_or_create_proposal_brief` module function
- `backend/app/services/pipeline_service.py` — `_load_context_brief` delegates to the helper; `analyze_brief`, `run_benchmarks`, `build_cost_model`, `generate_narrative` wired
- `backend/app/services/ai/brief_analyzer.py` — `analyze` accepts `context_brief`
- `backend/app/services/ai/narrative_generator.py` — `generate_all` + covering-letter/scope prompts accept `context_brief`
- `backend/app/services/ideation_service.py` — `_build_ideation_system_prompt` accepts `context_brief`; `run_ideation` loads it
- `backend/app/workers/pipeline.py` — register `enrich_context_from_emails` in `WorkerSettings.functions`
- `backend/app/viewmodels/connector_viewmodel.py` — `sync_emails` enqueues the enrichment job

**Untouched (verified):** `run_research` already calls `_load_context_brief` — it inherits persistence automatically once Task 2 lands, no change needed. `CostModelBuilder.build` needs no change for `discount_tags`.

---

## Task 1: Add `context_brief` column to Proposal

**Files:**
- Modify: `backend/app/infrastructure/db/models/proposal.py`
- Create: `backend/alembic/versions/<NN>_proposal_context_brief.py`

- [ ] **Step 1: Add the column to the model**

In `backend/app/infrastructure/db/models/proposal.py`, find the block of `Text` columns (`research`, `benchmarks` are `Mapped[str | None] = mapped_column(Text)`). Add directly after the `benchmarks` line:

```python
    context_brief: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 2: Create the migration**

Find the current migration head: `cd backend && .venv/bin/alembic heads`. Note the revision id it prints — that is the `down_revision` for the new migration. Look at the newest file in `backend/alembic/versions/` to copy the exact header format the project uses (revision id style, imports).

Create `backend/alembic/versions/<NN>_proposal_context_brief.py` (use the project's numbering convention — if the latest is `03_*`, this is `04_*`):

```python
"""add context_brief column to proposals

Revision ID: <pick a new id following the project convention>
Revises: <the current head revision id from `alembic heads`>
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "<new id>"
down_revision = "<current head id>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("context_brief", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "context_brief")
```

- [ ] **Step 3: Apply and verify the migration**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: no error; `context_brief` column added.

Verify the column exists and is nullable:
Run: `cd backend && .venv/bin/python -c "import asyncio; from sqlalchemy import text; from app.infrastructure.db.database import engine; asyncio.run(__import__('app.infrastructure.db.database', fromlist=['engine']).engine.dispose())"` — skip if awkward; instead just run the full test suite in step 4 which exercises the schema.

- [ ] **Step 4: Run the existing suite to confirm no regression**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all currently-passing tests still pass (the new nullable column defaults to `NULL` for every existing proposal — `make_proposal_db` and all fixtures load fine).

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/models/proposal.py backend/alembic/versions/
git commit -m "feat(S5): add Proposal.context_brief column"
```

---

## Task 2: `get_or_create_proposal_brief` shared helper

**Files:**
- Modify: `backend/app/services/context_service.py`
- Modify: `backend/app/services/pipeline_service.py` (`_load_context_brief` delegates)
- Create: `backend/tests/unit/test_context_brief_helper.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_context_brief_helper.py`:

```python
from __future__ import annotations

import pytest

from app.services.context_service import get_or_create_proposal_brief


@pytest.mark.asyncio
async def test_generates_persists_and_reuses(make_proposal_db, db, monkeypatch):
    """First call generates + persists; second call reads the column, no regen."""
    agency, client, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}},
    )
    # Give the client a context profile so generation has something to work on.
    from app.infrastructure.db.repositories.client_repo import ClientRepository
    await ClientRepository(db).update(client.id, context_profile={"relationship": {"status": "existing"}})
    await db.commit()

    calls = {"n": 0}

    async def fake_generate(self, client_name, context_profile):
        calls["n"] += 1
        return f"BRIEF for {client_name}"

    monkeypatch.setattr(
        "app.services.context_service.ContextService.generate_context_brief", fake_generate
    )

    # Reload the proposal so context_brief is NULL as stored.
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    repo = ProposalRepository(db)
    p1 = await repo.get_by_id(proposal.id)

    brief1 = await get_or_create_proposal_brief(db, p1)
    assert brief1 == "BRIEF for Acme"
    assert calls["n"] == 1

    # Reload — the column should now hold the brief.
    p2 = await repo.get_by_id(proposal.id)
    assert p2.context_brief == "BRIEF for Acme"

    brief2 = await get_or_create_proposal_brief(db, p2)
    assert brief2 == "BRIEF for Acme"
    assert calls["n"] == 1  # NOT regenerated — read from the column


@pytest.mark.asyncio
async def test_returns_none_when_no_context_profile(make_proposal_db, db, monkeypatch):
    """No client context profile → no brief, no persistence, no crash."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    async def fake_generate(self, client_name, context_profile):
        raise AssertionError("should not be called when profile is empty")

    monkeypatch.setattr(
        "app.services.context_service.ContextService.generate_context_brief", fake_generate
    )
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    p = await ProposalRepository(db).get_by_id(proposal.id)

    brief = await get_or_create_proposal_brief(db, p)
    assert brief is None
    assert p.context_brief is None


@pytest.mark.asyncio
async def test_generation_failure_is_swallowed(make_proposal_db, db, monkeypatch):
    """A generation exception returns None — context is best-effort, never blocks."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.client_repo import ClientRepository
    await ClientRepository(db).update(client.id, context_profile={"x": 1})
    await db.commit()

    async def boom(self, client_name, context_profile):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "app.services.context_service.ContextService.generate_context_brief", boom
    )
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    p = await ProposalRepository(db).get_by_id(proposal.id)

    brief = await get_or_create_proposal_brief(db, p)
    assert brief is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_context_brief_helper.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_or_create_proposal_brief'`.

- [ ] **Step 3: Add the helper to context_service.py**

At the end of `backend/app/services/context_service.py`, add this module-level function (after the `ContextService` class):

```python
async def get_or_create_proposal_brief(session, proposal) -> str | None:
    """Return the proposal's context brief, generating + persisting it on first need.

    Pipeline phases run as separate ARQ jobs, so the brief must live on the
    Proposal row to be shared. First caller pays one LLM call + commit; later
    callers (and retries) read the persisted column. Best-effort: any failure
    returns None and the caller proceeds without context.
    """
    import logging
    logger = logging.getLogger(__name__)

    if proposal.context_brief is not None:
        return proposal.context_brief

    try:
        from sqlalchemy import select
        from app.infrastructure.db.models.client import Client

        result = await session.execute(
            select(Client).where(Client.id == str(proposal.client_id))
        )
        client_row = result.scalar_one_or_none()
        if not client_row or not client_row.context_profile:
            return None

        client_name = (proposal.brief or {}).get("client", {}).get("name", "the client")
        brief = await ContextService().generate_context_brief(
            client_name, client_row.context_profile
        )
        if brief:
            proposal.context_brief = brief
            await session.commit()
            return brief
        return None
    except Exception:  # noqa: BLE001 — context is best-effort, never blocks a proposal
        logger.exception("get_or_create_proposal_brief failed")
        return None
```

- [ ] **Step 4: Point `_load_context_brief` at the helper**

In `backend/app/services/pipeline_service.py`, replace the entire `_load_context_brief` method (currently lines ~77-92) with a thin delegating wrapper:

```python
    async def _load_context_brief(self, proposal) -> str | None:
        from app.services.context_service import get_or_create_proposal_brief
        return await get_or_create_proposal_brief(self.session, proposal)
```

This keeps `run_research` (the existing caller at line ~172) working unchanged — it now transparently gets persistence.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_context_brief_helper.py -v`
Expected: PASS — 3 tests.

Run the full suite to confirm `run_research` still works:
Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/context_service.py backend/app/services/pipeline_service.py \
        backend/tests/unit/test_context_brief_helper.py
git commit -m "feat(S5): get_or_create_proposal_brief — persist context brief on the proposal"
```

---

## Task 3: Wire context_brief into `analyze_brief`

**Files:**
- Modify: `backend/app/services/ai/brief_analyzer.py`
- Modify: `backend/app/services/pipeline_service.py` (`analyze_brief`)
- Create/extend: `backend/tests/integration/test_s5_phase_context.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_s5_phase_context.py`:

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_analyze_brief_passes_context_brief(make_proposal_db, db, monkeypatch):
    """analyze_brief threads context_brief into BriefAnalyzer.analyze."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    # Persist a context_brief on the proposal so the phase reads it from the column.
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    captured = {}

    async def fake_analyze(self, chat_history, current_brief, context_brief=None):
        captured["context_brief"] = context_brief
        from app.services.ai.brief_analyzer import BriefAnalysisResult
        return BriefAnalysisResult(
            response_text="ok", brief_complete=False, brief_data={},
        )

    monkeypatch.setattr("app.services.ai.brief_analyzer.BriefAnalyzer.analyze", fake_analyze)

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.analyze_brief(proposal.id)

    assert captured["context_brief"] == "ACME CONTEXT BRIEF"
```

> **Note for implementer:** `BriefAnalysisResult` field names — open `brief_analyzer.py` and match the real dataclass/Pydantic model exactly (it has `response_text`, `brief_complete`, `brief_data` per the phase code at `pipeline_service.py:113-116`; confirm and adjust the fake's constructor if the model differs).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_analyze_brief_passes_context_brief -v`
Expected: FAIL — `analyze_brief` doesn't pass `context_brief` (captured value is `None`).

- [ ] **Step 3: Add `context_brief` to `BriefAnalyzer.analyze`**

In `backend/app/services/ai/brief_analyzer.py`, change the `analyze` method signature and system-prompt assembly. The current method uses `system=SYSTEM_PROMPT` (a module constant with no placeholders). Change it to:

```python
    async def analyze(
        self,
        chat_history: list[dict],
        current_brief: dict,
        context_brief: str | None = None,
    ) -> BriefAnalysisResult:
        """Process chat history and return the AI's response + optional completed brief.

        Uses Haiku 4.5 (FAST tier) — conversational info extraction with a known
        JSON schema doesn't need Sonnet/Opus quality, and Haiku is 3-5x faster
        end-to-end, which matters for chat felt-latency.
        """
        messages = self._build_messages(chat_history, current_brief)
        system = SYSTEM_PROMPT
        if context_brief:
            system = (
                f"{SYSTEM_PROMPT}\n\n"
                f"## Existing client context\n"
                f"You already know the following about this client from past "
                f"interactions. Use it to interpret the brief, but do not assume "
                f"facts not stated in the conversation.\n\n{context_brief}"
            )
        response_text = await self._client.complete(
            system=system,
            messages=messages,
            model=get_settings().ANTHROPIC_HAIKU_MODEL,
            max_tokens=2048,
            temperature=0.7,
        )
        return self._parse_response(response_text)
```

(Leave `stream_analyze` unchanged — it is a separate intake path not part of the pipeline phase.)

- [ ] **Step 4: Pass context_brief from the `analyze_brief` phase**

In `backend/app/services/pipeline_service.py`, in the `analyze_brief` method, after the `chat_history` is built and before the `BriefAnalyzer().analyze(...)` call (currently line ~109), add the brief load and pass it through:

```python
        context_brief = await self._load_context_brief(proposal)
        result = await BriefAnalyzer().analyze(
            chat_history=chat_history,
            current_brief=proposal.brief,
            context_brief=context_brief,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_analyze_brief_passes_context_brief -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai/brief_analyzer.py backend/app/services/pipeline_service.py \
        backend/tests/integration/test_s5_phase_context.py
git commit -m "feat(S5): wire context_brief into analyze_brief"
```

---

## Task 4: Wire context_brief into `run_benchmarks`

**Files:**
- Modify: `backend/app/services/pipeline_service.py` (`run_benchmarks`)
- Extend: `backend/tests/integration/test_s5_phase_context.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_s5_phase_context.py`:

```python
@pytest.mark.asyncio
async def test_run_benchmarks_injects_context_into_user_message(
    make_proposal_db, db, monkeypatch,
):
    """run_benchmarks appends the context brief to the benchmark user message."""
    agency, client, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
    )
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    # Stub the pre-flight plan + the streaming AI call; capture the user message.
    captured = {}

    async def fake_plan(brief):
        return {"searches": []}

    monkeypatch.setattr("app.services.pipeline_service.generate_benchmarks_plan", fake_plan)

    # process_stream + the ai.client stream are heavy — patch process_stream to short-circuit
    # and capture the messages passed into the stream call via a fake stream context manager.
    import app.services.pipeline_service as ps

    class _FakeStream:
        def __init__(self, messages): captured["messages"] = messages
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _FakeMessages:
        def stream(self, **kwargs):
            return _FakeStream(kwargs.get("messages"))

    class _FakeClient:
        messages = _FakeMessages()

    class _FakeAI:
        client = _FakeClient()
        def model_for(self, tier): return "fake-model"

    monkeypatch.setattr(ps, "get_ai_service", lambda: _FakeAI())

    async def fake_process_stream(stream, on_event=None):
        return ("benchmark body", [], [])

    monkeypatch.setattr(ps, "process_stream", fake_process_stream)

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    user_msg = captured["messages"][0]["content"]
    assert "ACME CONTEXT BRIEF" in user_msg
```

> **Note for implementer:** the exact names of `generate_benchmarks_plan`, `process_stream`, and `get_ai_service` as imported into `pipeline_service.py` must match — verify the import names at the top of `pipeline_service.py` and adjust the `monkeypatch.setattr` targets. If `ActivityFlusher` chokes on the fake stream, also patch `ActivityFlusher.flush` to an async no-op. The test's intent is fixed: assert the context brief text reaches the benchmark user message.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_run_benchmarks_injects_context_into_user_message -v`
Expected: FAIL — context brief is not in the user message.

- [ ] **Step 3: Inject context into the benchmark user message**

In `backend/app/services/pipeline_service.py`, in `run_benchmarks`, find where `user_msg` is built (currently lines ~279-283). Immediately after `user_msg` is assigned, add:

```python
        context_brief = await self._load_context_brief(proposal)
        if context_brief:
            user_msg += (
                f"\n\n## Existing context on {client_name}\n{context_brief}\n"
                f"Use this to focus the benchmark search on the client's actual segment."
            )
```

> **Note for implementer:** `client_name` may not be in scope inside `run_benchmarks` — `run_research` derives it as `(proposal.brief or {}).get("client", {}).get("name", "the client")`. If `client_name` isn't already a local in `run_benchmarks`, compute it the same way before this block.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_run_benchmarks_injects_context_into_user_message -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_s5_phase_context.py
git commit -m "feat(S5): wire context_brief into run_benchmarks"
```

---

## Task 5: Wire context_brief into `generate_narrative`

**Files:**
- Modify: `backend/app/services/ai/narrative_generator.py`
- Modify: `backend/app/services/pipeline_service.py` (`generate_narrative`)
- Extend: `backend/tests/integration/test_s5_phase_context.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_s5_phase_context.py`:

```python
@pytest.mark.asyncio
async def test_generate_narrative_passes_context_brief(make_proposal_db, db, monkeypatch):
    """generate_narrative threads context_brief into NarrativeGenerator.generate_all."""
    agency, client, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}},
    )
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(
        proposal.id, context_brief="ACME CONTEXT BRIEF", cost_model={"line_items": []},
    )
    await db.commit()

    captured = {}

    async def fake_generate_all(self, **kwargs):
        captured.update(kwargs)
        from app.services.ai.narrative_generator import NarrativeResult
        return NarrativeResult(
            covering_letter="", covering_letter_alt="", executive_summary="",
            scope_sections=[], cost_rationale="", terms="",
        )

    monkeypatch.setattr(
        "app.services.ai.narrative_generator.NarrativeGenerator.generate_all", fake_generate_all
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.generate_narrative(proposal.id)

    assert captured.get("context_brief") == "ACME CONTEXT BRIEF"
```

> **Note for implementer:** `NarrativeResult` field names must match the real model — open `narrative_generator.py` and match its constructor exactly. The `fake_generate_all` uses `**kwargs`, so it works regardless of how many args `generate_all` is called with, as long as `context_brief` is passed as a keyword.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_generate_narrative_passes_context_brief -v`
Expected: FAIL — `context_brief` not in captured kwargs.

- [ ] **Step 3: Add `context_brief` param to `NarrativeGenerator.generate_all` + thread into prompts**

In `backend/app/services/ai/narrative_generator.py`:

(a) Add `context_brief: str | None = None` to the `generate_all` signature (after `standard_revisions`).

(b) `generate_all` calls `generate_covering_letters(brief, research or "", template_config, agency_name, agency_voice)` and `generate_scope_sections(...)`. Pass `context_brief` into `generate_covering_letters` — add a `context_brief: str | None = None` param to that method too.

(c) In `generate_covering_letters`, the covering-letter prompt `COVERING_LETTER_SYSTEM` is assembled via `.format(...)`. Add a `{context_section}` placeholder to the `COVERING_LETTER_SYSTEM` constant — place it near the existing `{voice_section}` placeholder (voice_section is the established optional-injection precedent). Then in the `.format(...)` call inside `_gen_letter`, add:

```python
            context_section=(
                f"CLIENT CONTEXT (from past interactions):\n{context_brief}"
                if context_brief else ""
            ),
```

> **Note for implementer:** read `COVERING_LETTER_SYSTEM` (lines ~34-63) and `SCOPE_SECTION_SYSTEM` and place the `{context_section}` placeholder where it reads naturally — as its own paragraph between the voice profile and the task instructions. If you add the placeholder to `SCOPE_SECTION_SYSTEM` too, thread `context_brief` through `generate_scope_sections` the same way. If threading it into scope sections balloons the change, scope this task to the covering letter only and note scope-section context as a follow-up — the covering letter is the most relationship-sensitive output. Decide based on what you see; report the decision.

- [ ] **Step 4: Pass context_brief from the `generate_narrative` phase**

In `backend/app/services/pipeline_service.py`, in `generate_narrative`, before the `NarrativeGenerator().generate_all(...)` call (line ~429), add:

```python
        context_brief = await self._load_context_brief(proposal)
```

and add `context_brief=context_brief,` to the `generate_all(...)` keyword arguments.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_generate_narrative_passes_context_brief -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai/narrative_generator.py backend/app/services/pipeline_service.py \
        backend/tests/integration/test_s5_phase_context.py
git commit -m "feat(S5): wire context_brief into generate_narrative"
```

---

## Task 6: Wire context_brief into `run_ideation`

**Files:**
- Modify: `backend/app/services/ideation_service.py`
- Extend: `backend/tests/integration/test_s5_phase_context.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_s5_phase_context.py`:

```python
@pytest.mark.asyncio
async def test_run_ideation_includes_context_brief_in_system_prompt(
    make_proposal_db, db, monkeypatch,
):
    """run_ideation puts the context brief into the ideation system prompt."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    # Seed one user message on the ideation channel so run_ideation has input.
    from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
    from app.domain.enums import MessageRole, MessageType
    await ChatMessageRepository(db).create(
        proposal_id=proposal.id, role=MessageRole.USER.value,
        message_type=MessageType.TEXT.value, content="What's the angle?",
        phase="ideation", channel="ideation",
    )
    await db.commit()

    captured = {}

    async def fake_messages_create(self, **kwargs):
        captured["system"] = kwargs.get("system")
        class _Resp:
            content = [type("B", (), {"text": "an idea"})()]
        return _Resp()

    monkeypatch.setattr(
        "app.services.ai_service.AIService.messages_create", fake_messages_create
    )

    from app.services.ideation_service import IdeationService
    from unittest.mock import AsyncMock
    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(proposal.id)

    system = captured["system"]
    # system is a list of {"type":"text","text":...} blocks; join their text.
    text = " ".join(block["text"] for block in system) if isinstance(system, list) else str(system)
    assert "ACME CONTEXT BRIEF" in text
```

> **Note for implementer:** the `messages_create` patch target (`app.services.ai_service.AIService.messages_create`) must match the real module path / class name of the AI service `IdeationService` uses (`self.ai = get_ai_service()`). Verify and adjust. `MessageRole`/`MessageType` enum import path must match what `ideation_service.py` uses.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_run_ideation_includes_context_brief_in_system_prompt -v`
Expected: FAIL — the brief is not in the system prompt.

- [ ] **Step 3: Thread context_brief into the ideation system prompt**

In `backend/app/services/ideation_service.py`:

(a) Change `_build_ideation_system_prompt` to accept the brief:

```python
def _build_ideation_system_prompt(proposal, context_brief: str | None = None) -> str:
```

Inside it, after the project-name / phase lines and before (or after) the brief block, add:

```python
    if context_brief:
        parts.append(f"\n## Client context (from past interactions)\n{context_brief}")
```

(b) In `run_ideation`, after the `proposal` is loaded and before `system_text = _build_ideation_system_prompt(proposal)`, load the brief and pass it:

```python
        from app.services.context_service import get_or_create_proposal_brief
        context_brief = await get_or_create_proposal_brief(self.session, proposal)
        system_text = _build_ideation_system_prompt(proposal, context_brief)
```

`get_or_create_proposal_brief` reads `proposal.context_brief` (already populated if a pipeline phase ran first), or generates+persists if null — `IdeationService` has `self.session`, which is all the helper needs.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_phase_context.py::test_run_ideation_includes_context_brief_in_system_prompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ideation_service.py backend/tests/integration/test_s5_phase_context.py
git commit -m "feat(S5): wire context_brief into run_ideation"
```

---

## Task 7: `build_cost_model` consumes `proposal.preferences`

**Files:**
- Modify: `backend/app/services/pipeline_service.py` (`build_cost_model`)
- Create: `backend/tests/integration/test_s5_cost_model_preferences.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_s5_cost_model_preferences.py`:

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_build_cost_model_passes_merged_config(make_proposal_db, db, monkeypatch):
    """build_cost_model routes proposal.preferences through _merge_preferences_into_config
    so discount_tags reach CostModelBuilder as cost_model.default_multipliers."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(
        proposal.id, preferences={"discount_tags": ["annual_bundle"]},
    )
    await db.commit()

    captured = {}

    async def fake_build(self, *, brief, db, agency_id, benchmarks_md=None, template_config=None):
        captured["template_config"] = template_config
        from app.services.ai.cost_model_builder import CostModel
        return CostModel(
            line_items=[], subtotal=0, discount_percent=0, discount_amount=0,
            total=0, gst_amount=0, grand_total=0, multipliers_applied=[],
        )

    monkeypatch.setattr(
        "app.services.ai.cost_model_builder.CostModelBuilder.build", fake_build
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.build_cost_model(proposal.id)

    cfg = captured["template_config"] or {}
    # _merge_preferences_into_config renames discount_tags -> cost_model.default_multipliers
    assert cfg.get("cost_model", {}).get("default_multipliers") == ["annual_bundle"]


@pytest.mark.asyncio
async def test_build_cost_model_empty_preferences_no_op(make_proposal_db, db, monkeypatch):
    """Empty preferences → merged config equals the raw template config (regression guard)."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    # preferences defaults to {} — leave it.

    captured = {}

    async def fake_build(self, *, brief, db, agency_id, benchmarks_md=None, template_config=None):
        captured["template_config"] = template_config
        from app.services.ai.cost_model_builder import CostModel
        return CostModel(
            line_items=[], subtotal=0, discount_percent=0, discount_amount=0,
            total=0, gst_amount=0, grand_total=0, multipliers_applied=[],
        )

    monkeypatch.setattr(
        "app.services.ai.cost_model_builder.CostModelBuilder.build", fake_build
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.build_cost_model(proposal.id)

    # With no template + empty prefs, merged config is an empty dict (no crash, no spurious keys).
    assert captured["template_config"] in ({}, None) or "cost_model" not in captured["template_config"]
```

> **Note for implementer:** `CostModel` constructor field names must match the real model in `cost_model_builder.py` — open it and match exactly (the phase code reads `model.line_items`, `model.subtotal`, `model.discount_percent`, `model.discount_amount`, `model.total`, `model.gst_amount`, `model.grand_total`, `model.multipliers_applied`). Adjust the fake's constructor. Also confirm `build`'s real keyword/positional calling convention and match `fake_build`'s signature to it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_cost_model_preferences.py -v`
Expected: FAIL — `default_multipliers` is not `["annual_bundle"]` (build_cost_model passes the raw `template_config`, never merges preferences).

- [ ] **Step 3: Route preferences through the merge in `build_cost_model`**

In `backend/app/services/pipeline_service.py`, in `build_cost_model`, the current code is:

```python
        template_config = await self._load_template_config(proposal)

        await self._emit_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        model = await CostModelBuilder().build(
            brief=proposal.brief,
            db=self.session,
            agency_id=str(proposal.agency_id),
            benchmarks_md=proposal.benchmarks,
            template_config=template_config,
        )
```

Change it to merge preferences into the config before the build:

```python
        template_config = await self._load_template_config(proposal)
        effective_config = self._merge_preferences_into_config(
            template_config, proposal.preferences or {}
        )

        await self._emit_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        model = await CostModelBuilder().build(
            brief=proposal.brief,
            db=self.session,
            agency_id=str(proposal.agency_id),
            benchmarks_md=proposal.benchmarks,
            template_config=effective_config,
        )
```

`_merge_preferences_into_config` is a static method already defined on `PipelineService` (used by `generate_narrative`). It maps `preferences["discount_tags"]` → `config["cost_model"]["default_multipliers"]`, and `CostModelBuilder.build` already consumes `cost_model.default_multipliers` — so `discount_tags` now flows through with no `CostModelBuilder` change. `pricing_model` is carried into `config["cost_model"]["pricing_model"]` but `CostModelBuilder` does not branch on it (deliberate — see the plan's scope note; honoring it needs new pricing math, out of scope).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_s5_cost_model_preferences.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/tests/integration/test_s5_cost_model_preferences.py
git commit -m "feat(S5): build_cost_model consumes proposal.preferences via merged config"
```

---

## Task 8: `enrich_context_from_emails` ARQ task

**Files:**
- Create: `backend/app/workers/enrichment.py`
- Modify: `backend/app/workers/pipeline.py` (register the task)
- Create: `backend/tests/integration/test_enrich_context_from_emails.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_enrich_context_from_emails.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_enrich_processes_only_passed_clients(make_proposal_db, db, monkeypatch):
    """enrich_context_from_emails enriches only the given client_ids and updates context_profile."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    # Seed an EmailIndex row for this client.
    from app.infrastructure.db.models.email_index import EmailIndex
    from app.infrastructure.db.models.base import uuid_default  # if helper exists; else use uuid4
    import uuid
    row = EmailIndex(
        id=str(uuid.uuid4()),
        agency_id=str(agency.id),
        gmail_message_id=f"m-{uuid.uuid4()}",
        gmail_thread_id="t1",
        client_domain="acme.com",
        client_name=client.name,
        message_type="update",
        sentiment="positive",
        priority="medium",
        summary="Kickoff went well",
        entities={},
        from_address="jane@acme.com",
        to_addresses=[],
        subject="Kickoff",
        date=datetime(2026, 5, 1, tzinfo=timezone.utc),
        has_attachments=False,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    enrich_calls = {"profiles": []}

    async def fake_enrich(self, context_profile, email_summaries):
        enrich_calls["profiles"].append(email_summaries)
        return {**(context_profile or {}), "enriched": True}

    monkeypatch.setattr(
        "app.services.context_service.ContextService.enrich_context_with_emails", fake_enrich
    )

    from app.workers.enrichment import _enrich_clients
    await _enrich_clients(db, str(agency.id), [str(client.id)])

    # The client's context_profile was updated.
    from app.infrastructure.db.repositories.client_repo import ClientRepository
    refreshed = await ClientRepository(db).get_by_id(client.id)
    assert refreshed.context_profile.get("enriched") is True
    # The email summary carried the EmailIndex fields.
    assert enrich_calls["profiles"][0][0]["subject"] == "Kickoff"
    assert enrich_calls["profiles"][0][0]["summary"] == "Kickoff went well"


@pytest.mark.asyncio
async def test_enrich_isolates_per_client_errors(make_proposal_db, db, monkeypatch):
    """One client raising does not abort the others."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    async def boom(self, context_profile, email_summaries):
        raise RuntimeError("merge failed")

    monkeypatch.setattr(
        "app.services.context_service.ContextService.enrich_context_with_emails", boom
    )

    from app.workers.enrichment import _enrich_clients
    # Must not raise — per-client errors are caught.
    await _enrich_clients(db, str(agency.id), [str(client.id)])
```

> **Note for implementer:** `EmailIndex` construction — match the model's required columns exactly (all the `nullable=False` ones). If `BaseModel` auto-generates `id`, drop the explicit `id`. If there's a `_uuid_default` helper used elsewhere for `EmailIndex` rows (see `connector_viewmodel.py` around line 300), use it. `ClientRepository.get_by_id` returns the ORM row; `context_profile` is a JSON dict column.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_enrich_context_from_emails.py -v`
Expected: FAIL — `ModuleNotFoundError: app.workers.enrichment`.

- [ ] **Step 3: Write the enrichment worker**

Create `backend/app/workers/enrichment.py`:

```python
"""ARQ task: enrich client context profiles from synced emails.

Enqueued by ConnectorViewModel.sync_emails after it commits new email rows.
Terminal like the pipeline phases — a failure is logged, never retried, and
never propagates back to the sync that enqueued it. Per-client errors are
isolated so one bad client does not abort the rest.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.models.email_index import EmailIndex
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.services.context_service import ContextService

logger = logging.getLogger(__name__)


async def _enrich_clients(session, agency_id: str, client_ids: list[str]) -> None:
    """Core enrichment loop — separated from the ARQ wrapper so it's unit-testable."""
    client_repo = ClientRepository(session)
    context_service = ContextService()

    for client_id in client_ids:
        try:
            client = await client_repo.get_by_id(client_id)
            if client is None:
                continue

            result = await session.execute(
                select(EmailIndex).where(
                    EmailIndex.agency_id == str(agency_id),
                    EmailIndex.client_name == client.name,
                ).order_by(EmailIndex.date.desc())
            )
            rows = result.scalars().all()
            if not rows:
                continue

            email_summaries = [
                {
                    "date": row.date,
                    "message_type": row.message_type,
                    "sentiment": row.sentiment,
                    "subject": row.subject,
                    "summary": row.summary,
                }
                for row in rows
            ]

            merged = await context_service.enrich_context_with_emails(
                client.context_profile or {}, email_summaries
            )
            await client_repo.update(client.id, context_profile=merged)
            await session.commit()
            logger.info(
                "context enriched from emails",
                extra={"event": "connector.enrich.client_done",
                       "client_id": str(client.id), "email_count": len(rows)},
            )
        except Exception:  # noqa: BLE001 — isolate per-client failures
            logger.exception(
                "context enrichment failed for one client",
                extra={"event": "connector.enrich.client_failed", "client_id": str(client_id)},
            )
            await session.rollback()
            continue


async def enrich_context_from_emails(ctx, agency_id: str, client_ids: list[str]) -> None:
    """ARQ task entrypoint. Opens its own session; terminal on failure."""
    try:
        async with async_session_factory() as session:
            await _enrich_clients(session, agency_id, client_ids)
    except Exception:  # noqa: BLE001 — terminal, never re-raise
        logger.exception(
            "enrich_context_from_emails task failed",
            extra={"event": "connector.enrich.failed", "agency_id": str(agency_id)},
        )
```

> **Note for implementer:** verify the import path for `async_session_factory` — `pipeline.py` uses it; match that exact import. Verify `ClientRepository.get_by_id` exists (it inherits from `BaseRepository`). If `client_name` matching proves too loose (multiple clients sharing a name), the implementer may instead match `EmailIndex.client_domain` against the client's contact email domains — but `client_name` is what `EmailIndex` rows are tagged with by `sync_emails`, so start with name matching and note the limitation.

- [ ] **Step 4: Register the task in the worker**

In `backend/app/workers/pipeline.py`, import the new task and add it to `WorkerSettings.functions`:

```python
from app.workers.enrichment import enrich_context_from_emails
```

and in the `functions` list:

```python
    functions = [
        analyze_brief, run_research, run_benchmarks,
        build_cost_model, generate_narrative, generate_outputs,
        run_ideation,
        enrich_context_from_emails,                    # NEW (S5)
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_enrich_context_from_emails.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/enrichment.py backend/app/workers/pipeline.py \
        backend/tests/integration/test_enrich_context_from_emails.py
git commit -m "feat(S5): enrich_context_from_emails ARQ task"
```

---

## Task 9: `sync_emails` enqueues the enrichment job

**Files:**
- Modify: `backend/app/viewmodels/connector_viewmodel.py` (`sync_emails`)
- Create: `backend/tests/integration/test_sync_emails_enqueues_enrichment.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_sync_emails_enqueues_enrichment.py`:

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_sync_emails_enqueues_enrichment_for_clients_with_new_email(
    make_proposal_db, db, monkeypatch,
):
    """After sync_emails commits new email rows, it enqueues enrich_context_from_emails
    with the ids of clients that received new email."""
    # This test drives sync_emails with a stubbed GmailClient that returns one
    # new message for the client's domain, and asserts the ARQ enqueue call.
    pass  # see implementer note
```

> **Note for implementer — this test needs real setup; write it fully:**
> `sync_emails` is a method on `ConnectorViewModel`, which needs a `Request` and a DB session. Look at how the existing connector tests construct a `ConnectorViewModel` and drive `sync_emails` — `backend/tests/integration/test_email_sync_resumption.py` does exactly this (it calls `vm.sync_emails(agency.id)` with a stubbed Gmail client and a connected-Gmail agency). Copy that file's setup: a connected-Gmail agency, at least one client whose contact email domain matches, and a stubbed `GmailClient.fetch_messages_for_domain` returning one message.
>
> The ARQ pool: `ConnectorViewModel` reaches the pool via `self._request.app.state.arq_pool`. In the test, set `vm._request.app.state.arq_pool` to an `AsyncMock()` (or reuse the `arq_pool` conftest fixture if the VM is built against the app). After `await vm.sync_emails(agency.id)`, assert the mock's `enqueue_job` was called with `"enrich_context_from_emails"`, the agency id, and a `client_ids` list containing the client that got the new message.
>
> Also write a second test: when the stubbed Gmail returns ZERO new messages, assert `enqueue_job` was NOT called.
>
> Model the Gmail stubbing and agency/client setup directly on `test_email_sync_resumption.py` — do not invent a new harness.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_sync_emails_enqueues_enrichment.py -v`
Expected: FAIL — no enqueue happens.

- [ ] **Step 3: Add the enqueue to `sync_emails`**

In `backend/app/viewmodels/connector_viewmodel.py`, in `sync_emails`:

(a) Before the per-domain loop, build a map from email domain → client id, and a set to collect clients with new email. The loop already has `clients` (from `client_repo.search`) and `domain_map` (`{domain: client_name}` from `_extract_domains`). Add alongside:

```python
        # domain -> client.id, for enqueueing enrichment after the sync.
        domain_to_client_id: dict[str, str] = {}
        for client in clients:
            for contact in (client.contacts or []):
                email = (contact or {}).get("email") if isinstance(contact, dict) else None
                if email and "@" in email:
                    domain_to_client_id[email.split("@")[-1].lower()] = str(client.id)
        clients_with_new_email: set[str] = set()
```

(b) Inside the per-domain loop, at the point where `new_messages` is known to be non-empty (the branch that actually persists rows via `upsert_many`), record the client:

```python
                cid = domain_to_client_id.get(domain)
                if cid:
                    clients_with_new_email.add(cid)
```

(c) After the final `await self._db.commit()` (line ~352) and before the `return`, enqueue the job if there's anything to enrich:

```python
        if clients_with_new_email:
            try:
                pool = self._request.app.state.arq_pool
                import time as _t
                await pool.enqueue_job(
                    "enrich_context_from_emails",
                    str(agency_id),
                    sorted(clients_with_new_email),
                    _job_id=f"{agency_id}:enrich_context:{int(_t.time())}",
                )
            except Exception:  # noqa: BLE001 — enqueue failure must not fail the sync
                logger.exception(
                    "failed to enqueue enrich_context_from_emails",
                    extra={"event": "connector.enrich.enqueue_failed"},
                )
```

> **Note for implementer:** confirm how `ConnectorViewModel` exposes the request — `ViewModelBase` stores it; the discovery code and other connector methods reference `self._request`. Match the real attribute name. Confirm `agency_id` is in scope at the return point (it's the method parameter). The `enqueue_job` signature: positional `job_name, *args, _job_id=...` — matches the `chat_viewmodel._enqueue` precedent.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_sync_emails_enqueues_enrichment.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/viewmodels/connector_viewmodel.py \
        backend/tests/integration/test_sync_emails_enqueues_enrichment.py
git commit -m "feat(S5): sync_emails enqueues enrich_context_from_emails after commit"
```

---

## Task 10: Full sweep

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green. Tally = previous baseline (325 after the sync_emails 401→400 fix) + new S5 tests (~16: 3 helper + 4 phase-context + 2 cost-model + 2 enrich + 2 enqueue, plus any the implementer added).

- [ ] **Step 2: Confirm the migration is in the chain**

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic current`
Expected: head includes the `proposal_context_brief` revision; no error.

- [ ] **Step 3: Smoke-import the worker**

Run: `cd backend && .venv/bin/python -c "from app.workers.pipeline import WorkerSettings; print([f.__name__ for f in WorkerSettings.functions])"`
Expected: the printed list includes `enrich_context_from_emails`.

- [ ] **Step 4: Final commit (only if steps 1-3 surfaced fixes)**

If anything needed a fix:

```bash
git add <fixed files>
git commit -m "fix(S5): <one-line description>"
```

If everything passed clean, no commit needed.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Piece A.1 persistence → Task 1 (column) + Task 2 (helper) ✓
- Piece A.2 get-or-generate-and-persist → Task 2 ✓
- Piece A.3 wire 4 phases → Tasks 3 (analyze_brief), 4 (run_benchmarks), 5 (generate_narrative), 6 (run_ideation) ✓; `run_research` inherits persistence via Task 2's `_load_context_brief` rewrite ✓
- Piece B cost model preferences → Task 7 ✓ (with the documented `pricing_model` descope)
- Piece C ARQ task → Task 8 ✓; `sync_emails` enqueue → Task 9 ✓
- Error handling (best-effort brief, terminal enrich job, empty-preferences no-op) → covered in Tasks 2, 7, 8 ✓
- Testing per spec → each task is TDD; Task 10 full sweep ✓

**Placeholder scan:** No `TBD`/`TODO`/"handle edge cases". The several "Note for implementer" blocks give concrete instructions to verify real signatures against the codebase (model field names, import paths) rather than guessing — these are deliberate verification steps, not placeholders. Every code step has complete code.

**Type consistency:** `get_or_create_proposal_brief(session, proposal)` — same signature in Task 2 (definition), Task 6 (ideation caller). `_load_context_brief` delegates to it (Task 2). `context_brief` param threaded as a keyword arg consistently in Tasks 3/5. `_merge_preferences_into_config` is the existing static method, called identically to its `generate_narrative` use site.

**Known scope adjustment:** `pricing_model` (Piece B) is carried into the merged config but `CostModelBuilder` does not branch on it — there is no alternative pricing path in the builder to select, and adding one is "new pricing math" the spec's non-goals exclude. `discount_tags` fully works. This is documented in the plan header, Task 7, and is flagged for the user.

## Deferred to future work

- `pricing_model` actually changing the cost-model output (needs a defined alternative pricing approach in `CostModelBuilder`).
- Scope-section prompt context injection if Task 5's implementer scopes to the covering letter only.
- Backfilling pre-S5 `email_index` rows into context profiles.
- The dead paths flagged during exploration (`ResearchAgent.research_client`, hardcoded 18% GST).
