# S8 — Smart Rate Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent rate-card fallback with an explicit, just-in-time fill checkpoint that lets the user fill gaps manually, drag in an Excel rate-card spreadsheet, or skip to use defaults — without forcing rate-card completeness at onboarding.

**Architecture:** A new gap-analyzer LLM step runs at the end of `analyze_brief` and writes detected gaps to a new `proposals.rate_card_gaps` JSON column. The existing template-approval gate (the gate just before `run_research` is enqueued) is taught to NOT enqueue research when gaps exist. Three resume endpoints clear the gaps: manual fill (additively patches the agency rate card), skip (clears gaps without touching any rate card), and Excel import + confirm (writes a per-proposal `rate_card_override`). `CostModelBuilder` is changed so the rate-card source is resolved as override → agency master → fallback.

**Tech Stack:** FastAPI / SQLAlchemy async / Alembic / `AsyncAnthropicBedrock` via `AIService` / `openpyxl` (new dep) / ARQ / React + React Query + vitest + MSW.

**Spec:** `docs/superpowers/specs/2026-05-23-s8-smart-rate-card-design.md`

**Working directory:** all backend paths relative to `backend/`. All frontend paths relative to `frontend/`. The plan calls out which when it matters.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/alembic/versions/04_proposal_rate_card_columns.py` | Add `rate_card_gaps` and `rate_card_override` JSON columns | Create |
| `backend/app/infrastructure/db/models/proposal.py` | Declare the two new columns | Modify |
| `backend/app/services/ai/rate_gap_analyzer.py` | LLM-driven gap analysis (brief → needed roles/offerings) | Create |
| `backend/app/services/pipeline_service.py` | `analyze_brief` writes gaps post-commit | Modify |
| `backend/app/viewmodels/chat_viewmodel.py` | Template-gate pause if gaps exist | Modify |
| `backend/app/views/v1/proposals.py` | `/rate-card-gaps/fill`, `/rate-card-gaps/skip`, `/rate-card-import`, `/rate-card-import/confirm` endpoints | Modify |
| `backend/app/viewmodels/rate_card_viewmodel.py` | `add_missing_entries` viewmodel method | Modify |
| `backend/app/services/ai/cost_model_builder.py` | Override-first precedence + `source` field | Modify |
| `backend/app/services/rate_card_excel_parser.py` | `openpyxl` + LLM structured extraction | Create |
| `backend/pyproject.toml` | Add `openpyxl` dependency | Modify |
| `backend/tests/unit/test_rate_gap_analyzer.py` | Gap analyzer unit | Create |
| `backend/tests/integration/test_analyze_brief_gaps.py` | Gap detection integration | Create |
| `backend/tests/integration/test_rate_card_gaps_endpoints.py` | Fill / skip endpoints | Create |
| `backend/tests/integration/test_rate_card_import.py` | Excel upload + confirm | Create |
| `backend/tests/integration/test_cost_model_override.py` | Override-first precedence | Create |
| `frontend/src/api/proposals.ts` | New mutation hooks for fill/skip/import/confirm | Modify |
| `frontend/src/components/chat/rate-gap-card.tsx` | The chat fill-card with drop + form + preview | Create |
| `frontend/src/components/chat/cost-model-card.tsx` | Add `source` badge | Modify |
| `frontend/src/components/chat/chat-container.tsx` | Render `rate-gap-card` when gaps present | Modify |
| `frontend/src/components/chat/__tests__/rate-gap-card.test.tsx` | Card behaviour | Create |
| `docs/superpowers/HANDOFF.md` | Mark S8 complete | Modify |

---

### Task 1: Schema migration — `rate_card_gaps` and `rate_card_override` columns

**Files:**
- Create: `backend/alembic/versions/04_proposal_rate_card_columns.py`
- Modify: `backend/app/infrastructure/db/models/proposal.py`

- [ ] **Step 1: Add the columns to the SQLAlchemy model**

In `backend/app/infrastructure/db/models/proposal.py`, after the existing `pipeline_state: Mapped[dict] = mapped_column(JSONColumn, default=dict)` line (currently the last column declaration on line 51), add two new columns:

```python
    pipeline_state: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    rate_card_gaps: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    rate_card_override: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
```

- [ ] **Step 2: Create the Alembic migration**

Create `backend/alembic/versions/04_proposal_rate_card_columns.py`:

```python
"""add rate_card_gaps and rate_card_override columns to proposals

Revision ID: 04_proposal_rate_card_columns
Revises: 03_proposal_context_brief
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "04_proposal_rate_card_columns"
down_revision = "03_proposal_context_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("rate_card_gaps", sa.JSON(), nullable=True))
    op.add_column("proposals", sa.Column("rate_card_override", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposals", "rate_card_override")
    op.drop_column("proposals", "rate_card_gaps")
```

- [ ] **Step 3: Run the migration head check and the full backend test suite**

The tests use SQLite via the conftest setup which creates schema from `Base.metadata` directly — they do not run Alembic. So the model change alone is enough for the tests to pick up the new columns.

Run: `.venv/bin/python -m pytest -q`
Expected: **359 passed** (the S6+S7 baseline). No tests should fail from the column addition alone; nothing reads or writes the new columns yet.

- [ ] **Step 4: Commit**

```bash
git add backend/app/infrastructure/db/models/proposal.py backend/alembic/versions/04_proposal_rate_card_columns.py
git commit -m "feat(S8): add rate_card_gaps + rate_card_override columns to proposals"
```

---

### Task 2: Gap analyzer service

**Files:**
- Create: `backend/app/services/ai/rate_gap_analyzer.py`
- Create: `backend/tests/unit/test_rate_gap_analyzer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_rate_gap_analyzer.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

import app.services.ai.rate_gap_analyzer as rga
from app.services.ai.rate_gap_analyzer import analyze_gaps


@pytest.mark.asyncio
async def test_analyze_gaps_returns_lists_from_llm(monkeypatch):
    """The analyzer asks Claude to identify needed roles + offerings from the brief
    and returns them as plain lists. JSON parsing is delegated to AIService.complete_json."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(return_value={
        "needed_roles": ["senior_strategist", "junior_designer"],
        "needed_offerings": ["annual_retainer"],
    })
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({
        "client": {"name": "Horlicks"},
        "deliverables": ["Year-long brand campaign", "Monthly content"],
    })

    assert result == {
        "needed_roles": ["senior_strategist", "junior_designer"],
        "needed_offerings": ["annual_retainer"],
    }
    assert fake_ai.complete_json.await_count == 1


@pytest.mark.asyncio
async def test_analyze_gaps_returns_empty_on_llm_failure(monkeypatch):
    """If the LLM call raises, the analyzer logs and returns empty lists rather
    than blocking the pipeline. The cost-model fallback is the safety net."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(side_effect=RuntimeError("bedrock 5xx"))
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({"client": {"name": "Acme"}})

    assert result == {"needed_roles": [], "needed_offerings": []}


@pytest.mark.asyncio
async def test_analyze_gaps_returns_empty_on_malformed_response(monkeypatch):
    """If the LLM returns something that is not the expected shape, treat as no gaps."""
    fake_ai = AsyncMock()
    fake_ai.complete_json = AsyncMock(return_value={"unexpected": "shape"})
    monkeypatch.setattr(rga, "get_ai_service", lambda: fake_ai)

    result = await analyze_gaps({"client": {"name": "Acme"}})

    assert result == {"needed_roles": [], "needed_offerings": []}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_rate_gap_analyzer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ai.rate_gap_analyzer'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/ai/rate_gap_analyzer.py`:

```python
"""LLM-driven rate-card gap analyser.

Given a brief, asks Claude to identify the hourly roles and offering categories
that the cost-model phase will need to price the proposal. Returns plain
``{needed_roles: [str], needed_offerings: [str]}``. The diff against the actual
rate card is the caller's job — this module is pure inference.
"""
from __future__ import annotations

import json
import logging

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a costing assistant for a creative agency. Given a proposal brief,"
    " identify which hourly billing roles and which offering categories the"
    " agency's rate card would need to price this proposal."
    "\n\n"
    "Return STRICT JSON with two arrays of lowercase snake_case keys:"
    "\n"
    '  {"needed_roles": ["senior_strategist", "junior_designer"],'
    ' "needed_offerings": ["annual_retainer", "brand_identity"]}'
    "\n\n"
    "Keys must be lowercase snake_case identifiers an agency would naturally use in a rate card."
    " Do not invent specifics that aren't implied by the brief. Return empty arrays if unsure."
)


async def analyze_gaps(brief: dict) -> dict:
    """Return ``{"needed_roles": [...], "needed_offerings": [...]}`` for the brief.

    Failure-safe: on any LLM error or malformed response, returns empty lists.
    The cost-model fallback path is the safety net.
    """
    user_prompt = (
        "Brief:\n```json\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n```\n\nReturn the JSON described above."
    )

    try:
        result = await get_ai_service().complete_json(
            prompt=user_prompt,
            system=_SYSTEM,
            tier=Tier.BALANCED,
            max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "rate_gap_analyzer LLM call failed; treating as no gaps",
            extra={"event": "rate_gap.llm_failed", "error": str(exc)},
        )
        return {"needed_roles": [], "needed_offerings": []}

    if not isinstance(result, dict):
        return {"needed_roles": [], "needed_offerings": []}

    roles = result.get("needed_roles") or []
    offerings = result.get("needed_offerings") or []
    if not isinstance(roles, list):
        roles = []
    if not isinstance(offerings, list):
        offerings = []
    return {
        "needed_roles": [str(r) for r in roles if isinstance(r, (str, int))],
        "needed_offerings": [str(o) for o in offerings if isinstance(o, (str, int))],
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/unit/test_rate_gap_analyzer.py -q`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/rate_gap_analyzer.py backend/tests/unit/test_rate_gap_analyzer.py
git commit -m "feat(S8): add rate-card gap analyzer service"
```

---

### Task 3: Wire gap detection into `analyze_brief` + template-gate pause

**Files:**
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/app/viewmodels/chat_viewmodel.py`
- Create: `backend/tests/integration/test_analyze_brief_gaps.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_analyze_brief_gaps.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.infrastructure.db.models.rate_card import RateCard
from app.services.pipeline_service import PipelineService


@pytest.fixture
async def _agency_with_proposal(_schema, db_session):
    """Minimal fixture: an agency with one proposal and no rate card."""
    agency = Agency(name="Acme Studio")
    db_session.add(agency)
    await db_session.commit()
    from app.infrastructure.db.models.client import Client
    client = Client(agency_id=agency.id, name="Horlicks", slug="horlicks", contacts=[])
    db_session.add(client)
    proposal = Proposal(
        agency_id=agency.id, client_id=client.id,
        project_name="Year campaign", status=ProposalStatus.DRAFT.value,
        brief={"deliverables": ["brand strategy", "monthly content"]},
    )
    db_session.add(proposal)
    await db_session.commit()
    return agency, proposal


@pytest.mark.asyncio
async def test_analyze_brief_writes_rate_card_gaps_when_rate_card_empty(
    _agency_with_proposal, db_session, monkeypatch,
):
    """When the rate card is empty and the analyzer identifies needed entries,
    analyze_brief writes them to proposal.rate_card_gaps."""
    agency, proposal = _agency_with_proposal

    # Stub BriefAnalyzer to produce a complete brief
    from app.services.ai import brief_analyzer
    fake_result = AsyncMock()
    fake_result.brief_complete = True
    fake_result.brief_data = {"deliverables": ["brand strategy"]}
    fake_result.response_text = "Brief analyzed"
    monkeypatch.setattr(brief_analyzer.BriefAnalyzer, "analyze",
                        AsyncMock(return_value=fake_result))

    # Stub gap analyzer to return needed entries
    from app.services.ai import rate_gap_analyzer
    monkeypatch.setattr(rate_gap_analyzer, "analyze_gaps", AsyncMock(return_value={
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }))

    svc = PipelineService(db_session, redis=AsyncMock())
    await svc.analyze_brief(proposal.id)

    await db_session.refresh(proposal)
    assert proposal.rate_card_gaps is not None
    assert proposal.rate_card_gaps["missing_roles"] == ["senior_strategist"]
    assert proposal.rate_card_gaps["missing_offerings"] == ["annual_retainer"]
    assert proposal.rate_card_gaps["needed_roles"] == ["senior_strategist"]
    assert proposal.rate_card_gaps["needed_offerings"] == ["annual_retainer"]


@pytest.mark.asyncio
async def test_analyze_brief_no_gaps_when_rate_card_covers_everything(
    _agency_with_proposal, db_session, monkeypatch,
):
    """When the rate card already contains all needed entries, rate_card_gaps stays None."""
    agency, proposal = _agency_with_proposal
    rate_card = RateCard(
        agency_id=agency.id, is_active=True,
        offerings={"annual_retainer": {"name": "Annual Retainer", "base_price": 100}},
        hourly_rates={"senior_strategist": 4500},
    )
    db_session.add(rate_card)
    await db_session.commit()

    from app.services.ai import brief_analyzer
    fake_result = AsyncMock()
    fake_result.brief_complete = True
    fake_result.brief_data = {"deliverables": ["strategy"]}
    fake_result.response_text = "ok"
    monkeypatch.setattr(brief_analyzer.BriefAnalyzer, "analyze",
                        AsyncMock(return_value=fake_result))

    from app.services.ai import rate_gap_analyzer
    monkeypatch.setattr(rate_gap_analyzer, "analyze_gaps", AsyncMock(return_value={
        "needed_roles": ["senior_strategist"],
        "needed_offerings": ["annual_retainer"],
    }))

    svc = PipelineService(db_session, redis=AsyncMock())
    await svc.analyze_brief(proposal.id)

    await db_session.refresh(proposal)
    assert proposal.rate_card_gaps is None
```

(The `_schema` fixture and `db_session` fixture are the standard ones defined in `tests/conftest.py`. If `db_session` is named differently in this codebase, adapt — but the conftest follows the standard pattern.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_analyze_brief_gaps.py -q`
Expected: FAIL — `analyze_brief` doesn't yet call the gap analyzer, so `proposal.rate_card_gaps` stays None in the first test.

- [ ] **Step 3: Wire the gap analyzer into `analyze_brief`**

In `backend/app/services/pipeline_service.py`, add an import near the top:

```python
from app.services.ai.rate_gap_analyzer import analyze_gaps
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
```

In the `analyze_brief` method, immediately after the line that commits the brief update (`await self.proposal_repo.update(proposal.id, brief=result.brief_data)`, currently line 108), add a new private call. Replace the existing block:

```python
        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}
            await self.proposal_repo.update(proposal.id, brief=result.brief_data)
```

with:

```python
        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}
            await self.proposal_repo.update(proposal.id, brief=result.brief_data)
            await self._detect_rate_card_gaps(proposal, result.brief_data)
```

Then add the new private method, anywhere in the class (place it near `_load_context_brief` for proximity):

```python
    async def _detect_rate_card_gaps(self, proposal, brief: dict) -> None:
        """Identify hourly roles + offerings the cost-model phase will need that
        the agency's active rate card does not yet have, and persist them on
        the proposal. Pipeline pause is enforced later by the template-approval gate."""
        gaps_input = await analyze_gaps(brief)
        needed_roles = gaps_input["needed_roles"]
        needed_offerings = gaps_input["needed_offerings"]

        rc_repo = RateCardRepository(self.session)
        rate_card = await rc_repo.get_active(proposal.agency_id)

        existing_roles = set((rate_card.hourly_rates or {}).keys()) if rate_card else set()
        existing_offerings = set((rate_card.offerings or {}).keys()) if rate_card else set()

        missing_roles = [r for r in needed_roles if r not in existing_roles]
        missing_offerings = [o for o in needed_offerings if o not in existing_offerings]

        if not missing_roles and not missing_offerings:
            return  # nothing to write — proposal.rate_card_gaps stays NULL

        await self.proposal_repo.update(proposal.id, rate_card_gaps={
            "missing_roles": missing_roles,
            "missing_offerings": missing_offerings,
            "needed_roles": needed_roles,
            "needed_offerings": needed_offerings,
        })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_analyze_brief_gaps.py -q`
Expected: PASS — 2 passed.

- [ ] **Step 5: Pause the template-approval gate when gaps exist**

In `backend/app/viewmodels/chat_viewmodel.py`, the `approve_gate` method handles the `template` gate at lines 265-310. Find the block (currently around line 286-309):

```python
        if gate_id == "template":
            template_key = (gate_data or {}).get("template_key")
            if template_key:
                await self.proposal_repo.update(proposal.id, template_id=template_key)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["template_confirm"]
        elif gate_id == "cost_model":
            ...
```

Insert a gaps check after the template_key update but before the pipeline state update. The full revised `template` arm reads:

```python
        if gate_id == "template":
            template_key = (gate_data or {}).get("template_key")
            if template_key:
                await self.proposal_repo.update(proposal.id, template_id=template_key)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["template_confirm"]

            # If rate-card gaps were detected during analyze_brief, pause here.
            # The user must fill / skip / import-Excel before research can start.
            if proposal.rate_card_gaps:
                pipeline["current_phase"] = "rate_card_gaps"
                await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
                pause_msg = await self.msg_repo.create(
                    proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
                    message_type=MessageType.TEXT.value,
                    content=(
                        "Template confirmed. Before I cost this proposal I need a few "
                        "rates that aren't in your rate card yet — fill them, drop in a "
                        "rate-card spreadsheet, or skip to use estimated defaults."
                    ),
                    phase="rate_card_gaps",
                )
                await self._broadcast_msg(proposal_id, pause_msg)
                await ws_manager.broadcast(str(proposal_id), {
                    "type": "phase_change", "phase": "rate_card_gaps",
                })
                return pause_msg
        elif gate_id == "cost_model":
```

Note: the existing flow continues into the `pipeline["current_phase"] = next_phase` / enqueue block at the bottom of `approve_gate`. The `return pause_msg` short-circuits before that, so `run_research` is NOT enqueued when gaps exist.

- [ ] **Step 6: Add a test for the paused template-gate path**

Append to `backend/tests/integration/test_analyze_brief_gaps.py` (inside no test class — module-level functions):

```python
@pytest.mark.asyncio
async def test_template_gate_does_not_enqueue_research_when_gaps_exist(
    _agency_with_proposal, db_session, monkeypatch,
):
    """Approving the template gate must NOT enqueue run_research if
    proposal.rate_card_gaps is set."""
    from app.viewmodels.chat_viewmodel import ChatViewModel
    from unittest.mock import AsyncMock, MagicMock

    agency, proposal = _agency_with_proposal
    # Simulate that analyze_brief earlier wrote gaps
    proposal.rate_card_gaps = {
        "missing_roles": ["senior_strategist"], "missing_offerings": [],
        "needed_roles": ["senior_strategist"], "needed_offerings": [],
    }
    proposal.pipeline_state = {}
    await db_session.commit()

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id):
        enqueued.append(job_name)

    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    vm = ChatViewModel(request=MagicMock(), db=db_session, redis=AsyncMock())
    msg = await vm.approve_gate(proposal.id, agency.id, "template", {"template_key": "t1"})

    assert msg is not None
    assert enqueued == []  # no enqueue while gaps exist
    await db_session.refresh(proposal)
    assert proposal.pipeline_state.get("current_phase") == "rate_card_gaps"
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_analyze_brief_gaps.py -q`
Expected: PASS — 3 passed.

Also run the existing chat-viewmodel tests to confirm no regression on the happy-path template approval:
Run: `.venv/bin/python -m pytest backend/tests/integration/test_chat_api.py -q`
Expected: PASS (existing count unchanged).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/pipeline_service.py backend/app/viewmodels/chat_viewmodel.py backend/tests/integration/test_analyze_brief_gaps.py
git commit -m "feat(S8): detect rate-card gaps post-brief, pause template gate when present"
```

---

### Task 4: Manual fill + skip endpoints + viewmodel helper

**Files:**
- Modify: `backend/app/viewmodels/rate_card_viewmodel.py`
- Modify: `backend/app/views/v1/proposals.py`
- Create: `backend/tests/integration/test_rate_card_gaps_endpoints.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_rate_card_gaps_endpoints.py`:

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_fill_merges_into_agency_rate_card_and_clears_gaps(
    client, _registered_agency_with_proposal_and_gaps, monkeypatch,
):
    """POST /proposals/{id}/rate-card-gaps/fill merges submitted entries into the
    agency rate card and clears proposal.rate_card_gaps, then enqueues research."""
    agency, proposal, _api_headers = _registered_agency_with_proposal_and_gaps

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id):
        enqueued.append(job_name)

    from app.viewmodels.chat_viewmodel import ChatViewModel
    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-gaps/fill",
        headers=_api_headers,
        json={
            "hourly_rates": {"senior_strategist": 4500},
            "offerings": {"annual_retainer": {"name": "Annual Retainer", "base_price": 100000}},
        },
    )
    assert r.status_code == 200
    assert enqueued == ["run_research"]


@pytest.mark.asyncio
async def test_fill_rejects_keys_outside_detected_gaps(
    client, _registered_agency_with_proposal_and_gaps,
):
    """Caller can't sneak in keys that weren't in missing_roles/missing_offerings."""
    agency, proposal, _api_headers = _registered_agency_with_proposal_and_gaps

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-gaps/fill",
        headers=_api_headers,
        json={"hourly_rates": {"unrelated_role": 9999}, "offerings": {}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_skip_clears_gaps_without_touching_rate_card(
    client, _registered_agency_with_proposal_and_gaps, monkeypatch,
):
    """POST /proposals/{id}/rate-card-gaps/skip clears gaps and enqueues research
    without modifying the agency rate card."""
    agency, proposal, _api_headers = _registered_agency_with_proposal_and_gaps

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id):
        enqueued.append(job_name)

    from app.viewmodels.chat_viewmodel import ChatViewModel
    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-gaps/skip",
        headers=_api_headers,
    )
    assert r.status_code == 204
    assert enqueued == ["run_research"]
```

The `client` and `_registered_agency_with_proposal_and_gaps` fixtures are standard conftest fixtures: `client` is the `httpx.AsyncClient` against the FastAPI app; `_registered_agency_with_proposal_and_gaps` registers an agency + creates a proposal with `rate_card_gaps` set and returns the auth headers. If this fixture doesn't exist in conftest.py yet, add it alongside other agency fixtures — copying the pattern from `_registered_agency` (or whatever exists today) and additionally creating a proposal with `rate_card_gaps = {"missing_roles": ["senior_strategist"], "missing_offerings": ["annual_retainer"], "needed_roles": [...], "needed_offerings": [...]}`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_rate_card_gaps_endpoints.py -q`
Expected: FAIL — endpoints don't exist; 404 from FastAPI.

- [ ] **Step 3: Add the viewmodel helper that merges fill entries into the agency rate card**

In `backend/app/viewmodels/rate_card_viewmodel.py`, add a new method on `RateCardViewModel` (place it near `update_rate_card`):

```python
    async def add_missing_entries(
        self,
        agency_id: UUID,
        hourly_rates: dict[str, int],
        offerings: dict[str, dict],
    ) -> RateCard | None:
        """Additively merge new entries into the agency's active rate card.
        Existing keys are never overwritten. Returns the updated row, or None
        if no active rate card exists."""
        rc = await self.repo.get_active(agency_id)
        if rc is None:
            # No active rate card — create a fresh one with just these entries.
            new = RateCard(
                agency_id=agency_id, is_active=True,
                hourly_rates=hourly_rates,
                offerings=offerings,
            )
            self.db.add(new)
            await self.db.commit()
            await self.db.refresh(new)
            return new
        new_rates = {**(rc.hourly_rates or {})}
        for k, v in hourly_rates.items():
            if k not in new_rates:
                new_rates[k] = v
        new_offerings = {**(rc.offerings or {})}
        for k, v in offerings.items():
            if k not in new_offerings:
                new_offerings[k] = v
        rc.hourly_rates = new_rates
        rc.offerings = new_offerings
        await self.db.commit()
        await self.db.refresh(rc)
        return rc
```

`RateCard` import: ensure `from app.infrastructure.db.models.rate_card import RateCard` is present at the top of the file; add if not.

- [ ] **Step 4: Add the endpoints**

In `backend/app/views/v1/proposals.py`, add the two routes alongside the other proposal routes. Imports near the top of the file:

```python
from app.viewmodels.rate_card_viewmodel import RateCardViewModel
```

Then the routes (placement: after the proposal-CRUD routes but before any later sub-router includes):

```python
@router.post("/{proposal_id}/rate-card-gaps/fill", status_code=200)
async def fill_rate_card_gaps(
    proposal_id: UUID,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis_pool),
):
    """Merge submitted hourly_rates + offerings into the agency rate card,
    clear the proposal's gaps, and resume the pipeline (enqueue run_research)."""
    agency_id = request.state.agency_id
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not proposal.rate_card_gaps:
        raise HTTPException(status_code=400, detail="No rate-card gaps to fill")

    gaps = proposal.rate_card_gaps
    allowed_role_keys = set(gaps.get("missing_roles", []))
    allowed_offering_keys = set(gaps.get("missing_offerings", []))

    submitted_rates = body.get("hourly_rates") or {}
    submitted_offerings = body.get("offerings") or {}

    for k in submitted_rates:
        if k not in allowed_role_keys:
            raise HTTPException(status_code=400, detail=f"Role '{k}' is not in the detected gaps")
    for k in submitted_offerings:
        if k not in allowed_offering_keys:
            raise HTTPException(status_code=400, detail=f"Offering '{k}' is not in the detected gaps")

    rc_vm = RateCardViewModel(request, db)
    await rc_vm.add_missing_entries(
        agency_id=agency_id,
        hourly_rates=submitted_rates,
        offerings=submitted_offerings,
    )
    await proposal_repo.update(proposal_id, rate_card_gaps=None)
    await db.commit()

    await redis.enqueue_job(
        "run_research", str(proposal_id),
        _job_id=f"{proposal_id}:run_research",
    )
    return {"ok": True}


@router.post("/{proposal_id}/rate-card-gaps/skip", status_code=204)
async def skip_rate_card_gaps(
    proposal_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis_pool),
):
    """Clear the proposal's gaps without touching any rate card; resume the pipeline."""
    agency_id = request.state.agency_id
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not proposal.rate_card_gaps:
        return  # already cleared — idempotent

    await proposal_repo.update(proposal_id, rate_card_gaps=None)
    await db.commit()
    await redis.enqueue_job(
        "run_research", str(proposal_id),
        _job_id=f"{proposal_id}:run_research",
    )
```

If `get_redis_pool` doesn't already exist as a dependency in this codebase, it's the ARQ pool dependency — match whatever pattern the existing routes use to enqueue jobs (the chat-viewmodel uses `await pool.enqueue_job(...)`; copy that pattern).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_rate_card_gaps_endpoints.py -q`
Expected: PASS — 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/viewmodels/rate_card_viewmodel.py backend/app/views/v1/proposals.py backend/tests/integration/test_rate_card_gaps_endpoints.py
git commit -m "feat(S8): add manual fill + skip endpoints for rate-card gaps"
```

---

### Task 5: Cost-model override consumption + `source` field

**Files:**
- Modify: `backend/app/services/ai/cost_model_builder.py`
- Modify: `backend/app/services/pipeline_service.py`
- Create: `backend/tests/integration/test_cost_model_override.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_cost_model_override.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.ai.cost_model_builder import CostModelBuilder


@pytest.mark.asyncio
async def test_build_uses_override_when_present(monkeypatch):
    """When proposal.rate_card_override is set, CostModelBuilder uses it directly
    and tags the result with source='override'."""
    brief = {"deliverables": [{"name": "Strategy doc", "category": "strategy"}]}
    override = {
        "hourly_rates": {"senior_strategist": 5000},
        "offerings": {"strategy_pack": {"name": "Strategy Pack", "base_price": 200000}},
    }

    builder = CostModelBuilder()
    monkeypatch.setattr(builder, "_ai_match", AsyncMock(return_value=[]))
    model = await builder.build(
        brief=brief,
        rate_card_row=None,            # no agency rate card row
        rate_card_override=override,
        template_config={},
    )

    assert model.source == "override"


@pytest.mark.asyncio
async def test_build_uses_agency_when_no_override(monkeypatch):
    """Without an override, fall back to the agency rate card (existing behaviour)."""
    brief = {"deliverables": []}
    agency_rc = MagicMock()
    agency_rc.offerings = {"x": {"name": "x", "base_price": 1}}
    agency_rc.hourly_rates = {"r": 100}

    builder = CostModelBuilder()
    monkeypatch.setattr(builder, "_ai_match", AsyncMock(return_value=[]))
    model = await builder.build(
        brief=brief,
        rate_card_row=agency_rc,
        rate_card_override=None,
        template_config={},
    )

    assert model.source == "agency"


@pytest.mark.asyncio
async def test_build_uses_fallback_when_neither(monkeypatch):
    """Without an override or an agency rate card, fall back to the heuristic model."""
    builder = CostModelBuilder()
    model = await builder.build(
        brief={"deliverables": []},
        rate_card_row=None,
        rate_card_override=None,
        template_config={},
    )

    assert model.source == "fallback"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_cost_model_override.py -q`
Expected: FAIL — `CostModelBuilder.build` doesn't accept a `rate_card_override` kwarg and `CostModel` has no `source` field.

- [ ] **Step 3: Add the `source` field to the `CostModel` dataclass**

In `backend/app/services/ai/cost_model_builder.py`, find the `CostModel` dataclass (around line 55-70 based on the grep results). Add a `source` field:

```python
@dataclass
class CostModel:
    line_items: list[CostLineItem] = field(default_factory=list)
    # ... existing fields ...
    multipliers_applied: list[str] = field(default_factory=list)
    tiered: dict = field(default_factory=dict)
    source: str = "fallback"  # one of: "override" | "agency" | "fallback"
```

- [ ] **Step 4: Change `build()` to consult the override first**

The current `build` signature (line 78) starts roughly:

```python
    async def build(self, brief, rate_card_row, template_config):
        ...
```

Change the signature and the first branches. Replace the early portion of `build`:

```python
    async def build(
        self,
        brief: dict,
        rate_card_row=None,
        template_config: dict | None = None,
        rate_card_override: dict | None = None,
    ) -> CostModel:
        # Precedence: per-proposal override > agency master > fallback.
        if rate_card_override is not None:
            rate_card = {
                "offerings": rate_card_override.get("offerings", {}),
                "hourly_rates": rate_card_override.get("hourly_rates", {}),
            }
            source = "override"
        elif rate_card_row is not None:
            rate_card = {
                "offerings": rate_card_row.offerings,
                "hourly_rates": rate_card_row.hourly_rates,
            }
            source = "agency"
        else:
            model = self._fallback_model(brief)
            model.source = "fallback"
            return model
```

After this block, the rest of the method uses `rate_card` as today. At the END of `build`, right before each `return CostModel(...)` (or wherever the final CostModel is constructed), set `model.source = source`. If the existing code constructs `CostModel(line_items=..., ...)` and returns it, change to:

```python
        model = CostModel(line_items=line_items, ..., tiered=tiered_dict)
        model.source = source
        return model
```

Also update `_fallback_model` to set `model.source = "fallback"`:

```python
    def _fallback_model(self, brief: dict) -> CostModel:
        # existing body...
        model = CostModel(line_items=[...], ...)
        model.source = "fallback"
        return model
```

- [ ] **Step 5: Plumb `rate_card_override` from the pipeline into the builder call**

In `backend/app/services/pipeline_service.py`, find the `build_cost_model` method. It currently calls `CostModelBuilder().build(brief, rate_card_row, template_config)` (or similar — find the exact call). Change the call site to pass `rate_card_override=proposal.rate_card_override`:

```python
        cost_model = await CostModelBuilder().build(
            brief=proposal.brief or {},
            rate_card_row=rate_card_row,
            template_config=template_config,
            rate_card_override=proposal.rate_card_override,
        )
```

(Match the actual existing kwargs — the change is purely additive: add the new `rate_card_override=` kwarg.)

- [ ] **Step 6: Add `source` to the serialized cost_model dict so the frontend sees it**

The `model_to_dict` static method (around line 371 of `cost_model_builder.py`) serializes the model for storage. Ensure `source` is included:

```python
    @staticmethod
    def model_to_dict(model: CostModel) -> dict:
        return {
            # existing keys...
            "source": model.source,
        }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_cost_model_override.py backend/tests/unit/test_cost_model_builder.py backend/tests/integration/test_cost_model_build.py -q`
Expected: PASS — 3 new tests + all existing cost-model tests.

If the existing cost-model tests fail because they pass positional args to `build()` and the signature changed, update them to use keyword args. The kwarg-only changes should be backwards-compatible since `rate_card_row` and `template_config` are now both optional.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/ai/cost_model_builder.py backend/app/services/pipeline_service.py backend/tests/integration/test_cost_model_override.py
git commit -m "feat(S8): cost model consults rate_card_override first; expose source"
```

---

### Task 6: Excel import — parser, endpoints, openpyxl dep

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/services/rate_card_excel_parser.py`
- Modify: `backend/app/views/v1/proposals.py`
- Create: `backend/tests/integration/test_rate_card_import.py`

- [ ] **Step 1: Add openpyxl as a dependency**

In `backend/pyproject.toml`, add `openpyxl` to the `dependencies` array. The existing entries look like:

```toml
dependencies = [
    "fastapi>=...",
    "sqlalchemy>=...",
    # ...
]
```

Add an entry (alphabetically positioned):

```toml
    "openpyxl>=3.1.0",
```

Then sync the venv:

```bash
cd backend && uv sync
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/integration/test_rate_card_import.py`:

```python
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook
from unittest.mock import AsyncMock


def _build_sample_xlsx() -> bytes:
    """Build a tiny .xlsx with a rate-card-shaped sheet."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["Role", "Hourly rate (INR)"])
    ws.append(["Senior Strategist", 4500])
    ws.append(["Junior Designer", 1800])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_upload_returns_preview(
    client, _registered_agency_with_proposal_and_gaps, monkeypatch,
):
    """POST /rate-card-import accepts an xlsx + returns the parsed preview WITHOUT
    writing to rate_card_override yet."""
    _, proposal, headers = _registered_agency_with_proposal_and_gaps

    # Stub the LLM extraction call
    from app.services import rate_card_excel_parser
    fake_extracted = {
        "hourly_rates": {"senior_strategist": 4500, "junior_designer": 1800},
        "offerings": {},
        "multipliers": {},
        "low_confidence_fields": [],
    }
    monkeypatch.setattr(rate_card_excel_parser, "extract_with_llm",
                        AsyncMock(return_value=fake_extracted))

    xlsx_bytes = _build_sample_xlsx()
    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-import",
        headers=headers,
        files={"file": ("rates.xlsx", xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hourly_rates"] == fake_extracted["hourly_rates"]
    # NOT persisted yet
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository


@pytest.mark.asyncio
async def test_import_confirm_writes_override_and_resumes(
    client, db_session, _registered_agency_with_proposal_and_gaps, monkeypatch,
):
    """POST /rate-card-import/confirm writes proposal.rate_card_override,
    clears gaps, enqueues run_research."""
    agency, proposal, headers = _registered_agency_with_proposal_and_gaps

    enqueued: list[str] = []

    async def _fake_enqueue(self, job_name, proposal_id):
        enqueued.append(job_name)

    from app.viewmodels.chat_viewmodel import ChatViewModel
    monkeypatch.setattr(ChatViewModel, "_enqueue", _fake_enqueue)

    preview = {
        "hourly_rates": {"senior_strategist": 4500},
        "offerings": {},
    }
    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-import/confirm",
        headers=headers,
        json=preview,
    )
    assert r.status_code == 200

    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    repo = ProposalRepository(db_session)
    fresh = await repo.get_by_id(proposal.id)
    assert fresh.rate_card_override == preview
    assert fresh.rate_card_gaps is None
    assert enqueued == ["run_research"]


@pytest.mark.asyncio
async def test_import_rejects_non_xlsx(
    client, _registered_agency_with_proposal_and_gaps,
):
    """Non-xlsx upload returns 400."""
    _, proposal, headers = _registered_agency_with_proposal_and_gaps

    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-import",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_import_rejects_oversize(
    client, _registered_agency_with_proposal_and_gaps,
):
    """File larger than 5 MB returns 400."""
    _, proposal, headers = _registered_agency_with_proposal_and_gaps

    big = b"\x00" * (5 * 1024 * 1024 + 1)  # 5 MB + 1
    r = await client.post(
        f"/api/v1/proposals/{proposal.id}/rate-card-import",
        headers=headers,
        files={"file": ("big.xlsx", big,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_rate_card_import.py -q`
Expected: FAIL — endpoints / parser module not present yet.

- [ ] **Step 4: Implement the Excel parser**

Create `backend/app/services/rate_card_excel_parser.py`:

```python
"""Parse a .xlsx rate-card spreadsheet into a structured rate-card via LLM extraction.

Two-step: openpyxl reads the cells into a JSON-of-rows structure; AIService.complete_json
asks Claude to extract the rate card from that. The LLM call is the fuzzy part —
spreadsheets in the wild have arbitrary layouts, so structured extraction beats heuristics.
"""
from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.services.llm import Tier, get_ai_service

logger = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB

_EXTRACT_SYSTEM = (
    "You extract structured rate cards from spreadsheets for a creative agency."
    " Given the cells of one or more sheets, return STRICT JSON with this schema:"
    "\n"
    '  {"hourly_rates": {"role_key": rate_inr_int, ...},'
    ' "offerings": {"offering_key": {"name": "Display Name", "base_price": int}, ...},'
    ' "multipliers": {"key": percent_float, ...},'
    ' "low_confidence_fields": ["role.foo", "offering.bar"]}'
    "\n\n"
    "Keys are lowercase snake_case identifiers. Numeric values are INR rupees as ints"
    " unless the sheet clearly indicates a percentage. Leave any key you can't infer"
    " confidently out of the output; list it in low_confidence_fields with a brief locator."
    " Do not invent rates. Return empty objects rather than guessing."
)


def parse_workbook(content: bytes) -> list[dict]:
    """Read the workbook into a list of sheets, each with rows of cells."""
    wb = load_workbook(filename=BytesIO(content), data_only=True, read_only=True)
    sheets = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [{"value": v} for v in row]
            rows.append({"cells": cells})
        sheets.append({"name": sheet_name, "rows": rows})
    return sheets


async def extract_with_llm(sheets: list[dict]) -> dict:
    """Send the parsed sheets to Claude and ask for a structured rate card."""
    user_prompt = (
        "Spreadsheet contents:\n```json\n"
        + json.dumps(sheets, ensure_ascii=False, indent=2, default=str)[:50_000]
        + "\n```\n\nReturn the JSON described in the system prompt."
    )

    result = await get_ai_service().complete_json(
        prompt=user_prompt,
        system=_EXTRACT_SYSTEM,
        tier=Tier.BALANCED,
        max_tokens=2000,
    )

    if not isinstance(result, dict):
        raise ValueError("LLM returned a non-dict response")

    return {
        "hourly_rates": result.get("hourly_rates") or {},
        "offerings": result.get("offerings") or {},
        "multipliers": result.get("multipliers") or {},
        "low_confidence_fields": result.get("low_confidence_fields") or [],
    }


async def parse_and_extract(content: bytes) -> dict:
    """Top-level helper used by the upload endpoint."""
    sheets = parse_workbook(content)
    return await extract_with_llm(sheets)
```

- [ ] **Step 5: Add the upload + confirm endpoints**

In `backend/app/views/v1/proposals.py`, add:

```python
from fastapi import UploadFile, File
from app.services.rate_card_excel_parser import (
    MAX_BYTES, parse_and_extract,
)


@router.post("/{proposal_id}/rate-card-import", status_code=200)
async def import_rate_card_xlsx(
    proposal_id: UUID,
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    agency_id = request.state.agency_id
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit")

    try:
        preview = await parse_and_extract(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse spreadsheet: {exc}")

    return preview  # NOT persisted — frontend must call /confirm with the (possibly edited) preview


@router.post("/{proposal_id}/rate-card-import/confirm", status_code=200)
async def confirm_rate_card_import(
    proposal_id: UUID,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis_pool),
):
    """Accept the (possibly user-edited) preview and write it to proposal.rate_card_override."""
    agency_id = request.state.agency_id
    proposal_repo = ProposalRepository(db)
    proposal = await proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    override = {
        "hourly_rates": body.get("hourly_rates") or {},
        "offerings": body.get("offerings") or {},
        "multipliers": body.get("multipliers") or {},
    }

    await proposal_repo.update(
        proposal_id,
        rate_card_override=override,
        rate_card_gaps=None,
    )
    await db.commit()

    await redis.enqueue_job(
        "run_research", str(proposal_id),
        _job_id=f"{proposal_id}:run_research",
    )
    return {"ok": True}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/integration/test_rate_card_import.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/services/rate_card_excel_parser.py backend/app/views/v1/proposals.py backend/tests/integration/test_rate_card_import.py
git commit -m "feat(S8): Excel rate-card import with two-step preview/confirm"
```

---

### Task 7: Frontend — rate-gap-card with manual fill, skip, Excel drop, preview, confirm

**Files:**
- Modify: `frontend/src/api/proposals.ts`
- Create: `frontend/src/components/chat/rate-gap-card.tsx`
- Modify: `frontend/src/components/chat/chat-container.tsx`
- Create: `frontend/src/components/chat/__tests__/rate-gap-card.test.tsx`

- [ ] **Step 1: Add the API hooks**

In `frontend/src/api/proposals.ts`, add four new mutation hooks. The file already exports `useProposalDetail`, `useApproveGate`, etc. Add alongside:

```ts
export function useFillRateCardGaps(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      hourly_rates: Record<string, number>
      offerings: Record<string, { name: string; base_price: number }>
    }) => {
      const { data } = await api.post(
        `/proposals/${proposalId}/rate-card-gaps/fill`,
        body,
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposal', proposalId] }),
  })
}

export function useSkipRateCardGaps(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.post(`/proposals/${proposalId}/rate-card-gaps/skip`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposal', proposalId] }),
  })
}

export function useImportRateCardXlsx(proposalId: string) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post(
        `/proposals/${proposalId}/rate-card-import`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return data as {
        hourly_rates: Record<string, number>
        offerings: Record<string, { name: string; base_price: number }>
        multipliers: Record<string, number>
        low_confidence_fields: string[]
      }
    },
  })
}

export function useConfirmRateCardImport(proposalId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (preview: {
      hourly_rates: Record<string, number>
      offerings: Record<string, { name: string; base_price: number }>
      multipliers?: Record<string, number>
    }) => {
      await api.post(
        `/proposals/${proposalId}/rate-card-import/confirm`,
        preview,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposal', proposalId] }),
  })
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/chat/__tests__/rate-gap-card.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { RateGapCard } from '../rate-gap-card'

const SAMPLE_GAPS = {
  missing_roles: ['senior_strategist'],
  missing_offerings: ['annual_retainer'],
  needed_roles: ['senior_strategist'],
  needed_offerings: ['annual_retainer'],
}

describe('RateGapCard', () => {
  it('renders one input per missing role and offering', () => {
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)
    expect(screen.getByLabelText(/senior strategist/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/annual retainer/i)).toBeInTheDocument()
  })

  it('submits filled values to /rate-card-gaps/fill', async () => {
    const user = userEvent.setup()
    let body: any = null
    server.use(
      http.post(`${API}/proposals/p1/rate-card-gaps/fill`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    await user.type(screen.getByLabelText(/senior strategist/i), '4500')
    // For an offering, the card renders name + base price inputs. The name
    // defaults to a humanized form of the key; base price is the numeric input.
    await user.type(screen.getByLabelText(/annual retainer.*price/i), '1500000')

    await user.click(screen.getByRole('button', { name: /fill and continue/i }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body.hourly_rates.senior_strategist).toBe(4500)
    expect(body.offerings.annual_retainer.base_price).toBe(1500000)
  })

  it('calls /rate-card-gaps/skip when Skip is clicked', async () => {
    const user = userEvent.setup()
    let called = false
    server.use(
      http.post(`${API}/proposals/p1/rate-card-gaps/skip`, () => {
        called = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    await user.click(screen.getByRole('button', { name: /skip/i }))
    await waitFor(() => expect(called).toBe(true))
  })

  it('shows the preview after a successful Excel upload, then confirm', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/proposals/p1/rate-card-import`, () =>
        HttpResponse.json({
          hourly_rates: { senior_strategist: 4500 },
          offerings: {},
          multipliers: {},
          low_confidence_fields: [],
        }),
      ),
      http.post(`${API}/proposals/p1/rate-card-import/confirm`, () =>
        HttpResponse.json({ ok: true }),
      ),
    )
    renderWithProviders(<RateGapCard proposalId="p1" gaps={SAMPLE_GAPS} />)

    // Programmatically dispatch a drop with an .xlsx file
    const file = new File(['fake'], 'rates.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const input = screen.getByLabelText(/upload rate card spreadsheet/i) as HTMLInputElement
    await user.upload(input, file)

    await waitFor(() =>
      expect(screen.getByText(/senior_strategist/i)).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() =>
      expect(screen.queryByText(/senior_strategist/i)).not.toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pnpm test -- src/components/chat/__tests__/rate-gap-card.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 4: Implement the component**

Create `frontend/src/components/chat/rate-gap-card.tsx`:

```tsx
import { useState } from 'react'
import {
  useFillRateCardGaps,
  useSkipRateCardGaps,
  useImportRateCardXlsx,
  useConfirmRateCardImport,
} from '../../api/proposals'

interface Gaps {
  missing_roles: string[]
  missing_offerings: string[]
  needed_roles: string[]
  needed_offerings: string[]
}

interface PreviewShape {
  hourly_rates: Record<string, number>
  offerings: Record<string, { name: string; base_price: number }>
  multipliers?: Record<string, number>
  low_confidence_fields?: string[]
}

interface Props {
  proposalId: string
  gaps: Gaps
}

function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function RateGapCard({ proposalId, gaps }: Props) {
  const fill = useFillRateCardGaps(proposalId)
  const skip = useSkipRateCardGaps(proposalId)
  const imp = useImportRateCardXlsx(proposalId)
  const confirm = useConfirmRateCardImport(proposalId)

  const [rateValues, setRateValues] = useState<Record<string, string>>({})
  const [offeringValues, setOfferingValues] = useState<
    Record<string, { name: string; base_price: string }>
  >(() =>
    Object.fromEntries(
      gaps.missing_offerings.map(k => [k, { name: humanize(k), base_price: '' }]),
    ),
  )
  const [preview, setPreview] = useState<PreviewShape | null>(null)

  const onSubmitManual = () => {
    const hourly_rates: Record<string, number> = {}
    for (const k of gaps.missing_roles) {
      const v = parseInt(rateValues[k] ?? '', 10)
      if (!Number.isNaN(v)) hourly_rates[k] = v
    }
    const offerings: Record<string, { name: string; base_price: number }> = {}
    for (const k of gaps.missing_offerings) {
      const o = offeringValues[k]
      const v = parseInt(o.base_price, 10)
      if (!Number.isNaN(v)) {
        offerings[k] = { name: o.name || humanize(k), base_price: v }
      }
    }
    fill.mutate({ hourly_rates, offerings })
  }

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const result = await imp.mutateAsync(file).catch(() => null)
    if (result) setPreview(result)
  }

  const onConfirmPreview = () => {
    if (!preview) return
    confirm.mutate(preview)
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 space-y-4">
      <p className="text-sm text-stone-700">
        I need a few rates to price this proposal. Drop in your rate-card spreadsheet,
        fill the fields manually, or skip to use estimated defaults.
      </p>

      {preview ? (
        <div className="rounded-lg bg-white border border-stone-200 p-3 space-y-2">
          <h4 className="text-sm font-medium text-stone-900">Parsed preview</h4>
          <pre className="text-xs text-stone-700 whitespace-pre-wrap">
            {JSON.stringify(preview, null, 2)}
          </pre>
          <div className="flex gap-2">
            <button
              onClick={onConfirmPreview}
              disabled={confirm.isPending}
              className="rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {confirm.isPending ? 'Confirming…' : 'Confirm and continue'}
            </button>
            <button
              onClick={() => setPreview(null)}
              className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <label className="block">
            <span className="text-xs text-stone-600">Upload rate card spreadsheet (.xlsx)</span>
            <input
              type="file"
              accept=".xlsx"
              aria-label="Upload rate card spreadsheet"
              onChange={onFileChange}
              className="mt-1 block w-full text-sm"
            />
          </label>

          <div className="border-t border-amber-200 pt-3 space-y-2">
            <p className="text-xs text-stone-600">Or fill manually:</p>
            {gaps.missing_roles.map(role => (
              <div key={role} className="flex items-center gap-2">
                <label className="text-xs text-stone-700 w-44" htmlFor={`role-${role}`}>
                  {humanize(role)}
                </label>
                <input
                  id={`role-${role}`}
                  aria-label={humanize(role)}
                  type="number"
                  value={rateValues[role] ?? ''}
                  onChange={e => setRateValues(s => ({ ...s, [role]: e.target.value }))}
                  className="rounded-md border border-stone-300 px-2 py-1 text-xs w-32"
                  placeholder="₹/hr"
                />
              </div>
            ))}
            {gaps.missing_offerings.map(off => (
              <div key={off} className="space-y-1 border-t border-amber-200/50 pt-2">
                <label className="text-xs text-stone-700 block">{humanize(off)}</label>
                <input
                  aria-label={`${humanize(off)} name`}
                  type="text"
                  value={offeringValues[off]?.name ?? humanize(off)}
                  onChange={e => setOfferingValues(s => ({
                    ...s, [off]: { ...s[off], name: e.target.value }
                  }))}
                  className="rounded-md border border-stone-300 px-2 py-1 text-xs w-full"
                  placeholder="Display name"
                />
                <input
                  aria-label={`${humanize(off)} price`}
                  type="number"
                  value={offeringValues[off]?.base_price ?? ''}
                  onChange={e => setOfferingValues(s => ({
                    ...s, [off]: { ...s[off], base_price: e.target.value }
                  }))}
                  className="rounded-md border border-stone-300 px-2 py-1 text-xs w-full"
                  placeholder="Base price (₹)"
                />
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={onSubmitManual}
              disabled={fill.isPending}
              className="rounded-lg bg-stone-900 px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {fill.isPending ? 'Saving…' : 'Fill and continue'}
            </button>
            <button
              onClick={() => skip.mutate()}
              disabled={skip.isPending}
              className="rounded-lg border border-stone-300 px-4 py-1.5 text-xs font-medium text-stone-700"
            >
              {skip.isPending ? 'Skipping…' : 'Skip — use defaults'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Render the card in the chat container**

In `frontend/src/components/chat/chat-container.tsx`, find where existing per-phase cards are conditionally rendered (the file pattern: `if (proposal.something) { return <SomeCard ... /> }`). Add a condition for `rate_card_gaps`:

```tsx
import { RateGapCard } from './rate-gap-card'
// ...

// In the render — choose the right place by pipeline_state.current_phase. If the
// project pattern is `if (proposal.pipeline_state?.current_phase === 'rate_card_gaps')`,
// match that pattern. Otherwise gate on `proposal.rate_card_gaps != null`:
{proposal.rate_card_gaps != null ? (
  <RateGapCard proposalId={proposal.id} gaps={proposal.rate_card_gaps} />
) : null}
```

Place this block alongside the existing per-phase card branches (e.g. after the approval-gate branch and before the cost-model-card branch).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pnpm test -- src/components/chat/__tests__/rate-gap-card.test.tsx`
Expected: PASS — 4 passed.

Run the full frontend suite to confirm no regressions:
Run: `pnpm test`
Expected: PASS, exit 0. Frontend baseline was 256; expect 260.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/proposals.ts frontend/src/components/chat/rate-gap-card.tsx frontend/src/components/chat/chat-container.tsx frontend/src/components/chat/__tests__/rate-gap-card.test.tsx
git commit -m "feat(S8): rate-gap chat card with fill, skip, Excel drop + preview"
```

---

### Task 8: Full regression + docs

**Files:**
- Modify: `docs/superpowers/HANDOFF.md`

- [ ] **Step 1: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 359 baseline + 12 new tests (3 gap-analyzer + 3 gaps integration + 3 gaps endpoints + 3 cost-model override + 4 import — actually 13 tests; if the count is slightly different, the spread across the new test files is what matters). Acceptable range: **371–373 passing.** Exit 0.

- [ ] **Step 2: Run the full frontend suite**

Run: `pnpm test`
Expected: 256 baseline + 4 new rate-gap-card tests = **260 passing**. Exit 0.

- [ ] **Step 3: Update `docs/superpowers/HANDOFF.md`**

(a) Top "Last updated" block — change the date/headline:

```
**Last updated:** 2026-05-23 (S8 smart rate card shipped + deployed)
**Latest commit on `main`:** `<post-S7-tidy>` (S7 + tidy). S8 lives on branch `worktree-s8-smart-rate-card` pending merge.
**Working tree:** clean inside the S8 worktree. `main` is still in sync with `origin/main`.
```

Look up the actual current `main` HEAD short SHA via `git -C <repo-root> rev-parse --short main` to fill in `<post-S7-tidy>`.

(b) The roadmap status line still says "S1–S7 COMPLETE. All M16-M20 work is fully shipped." Append S8 as a separate slice on top of that:

```
**M16-M20 roadmap status:** S1–S7 COMPLETE. All M16-M20 work — backend + frontend — is fully shipped.
**Post-roadmap slices:** S8 (smart rate card) COMPLETE — see "What happened this session" below.
```

(c) Insert a new session section immediately above the existing "What happened this session (2026-05-23 — S7)" section. Heading: `## What happened this session (2026-05-23 — S8)`. Content:

```markdown
## What happened this session (2026-05-23 — S8)

Shipped **S8 — smart rate card**: rate-card gaps are now detected the moment the brief is analysed, surface as a chat fill-card after the template gate, and can be resolved three ways — manual fill (additive to the agency rate card), Excel import (per-proposal override), or skip (use estimated defaults).

### Architecture

- **Gap detection (backend).** New `services/ai/rate_gap_analyzer.py`. `PipelineService.analyze_brief` calls it post-commit and writes `proposal.rate_card_gaps` if the agency's active rate card is missing any needed entries.
- **Pause point (backend).** `ChatViewModel.approve_gate("template", ...)` short-circuits if `rate_card_gaps` is set — `run_research` is NOT enqueued until the gaps are cleared.
- **Resume paths (backend).** Three endpoints under `/proposals/{id}/rate-card-gaps`: `/fill` (merges into agency master), `/skip` (clears without modifying), and the `/rate-card-import` + `/rate-card-import/confirm` pair (writes per-proposal override). All three enqueue `run_research`.
- **Cost-model precedence (backend).** `CostModelBuilder.build` now consults override → agency → fallback in that order and stamps `cost_model.source` so the frontend can show which one was used.
- **Excel parsing (backend).** New `services/rate_card_excel_parser.py` uses `openpyxl` for the read and `AIService.complete_json` for the structured extraction. Two-step preview/confirm so the user sees what the LLM extracted before it locks in.
- **Chat fill-card (frontend).** New `components/chat/rate-gap-card.tsx` renders when `proposal.rate_card_gaps != null`. Three actions in one card: manual fill form, Excel drop, skip.

### Schema

Migration `04_proposal_rate_card_columns` adds two nullable JSON columns to `proposals`: `rate_card_gaps` and `rate_card_override`. No backfill.

### Test counts

- Backend: 359 → 371–373 (12-13 new across gap-analyzer, integration, endpoints, override, import)
- Frontend: 256 → 260 (4 new for the rate-gap-card)

### Non-goals (deferred)

- Multi-dimensional rate cards (per-client / per-job overrides at the agency master level).
- Editing existing rate-card entries from the chat — fill only ever ADDS.
- `.csv` / `.xls` / Google Sheets import (only `.xlsx` for now).
- Multi-currency rates.
- Saving an imported override back to the agency master.
```

- [ ] **Step 4: Verify the migration is the new head**

Run: `cd backend && .venv/bin/python -m alembic heads`
Expected: a single head `04_proposal_rate_card_columns`. If multiple heads appear, something else added a migration that needs merging — flag it.

- [ ] **Step 5: Commit the doc change**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S8): mark S8 complete; smart rate card shipped"
```

---

## Self-review notes

- **Spec coverage:** Piece A (gap detection) → Task 2 + Task 3; Piece B (manual fill / skip) → Task 4; Piece C (Excel import) → Task 6; Piece D (cost-model override) → Task 5; Piece E (schema) → Task 1; UI → Task 7; regression + docs → Task 8.
- **Naming consistency:** `rate_card_gaps`, `rate_card_override`, `missing_roles`, `missing_offerings`, `needed_roles`, `needed_offerings`, `source`, `analyze_gaps`, `extract_with_llm`, `add_missing_entries` — used identically across backend, tests, and frontend.
- **Endpoint paths:** all under `/api/v1/proposals/{id}/rate-card-gaps/*` and `/api/v1/proposals/{id}/rate-card-import[/confirm]` — consistent.
- **Schema:** one migration, two nullable JSON columns, no backfill required.
- **The auth header pattern:** the fixture `_registered_agency_with_proposal_and_gaps` is referenced from existing conftest patterns. If the actual conftest fixture name differs in this codebase, the implementer must adapt the test to the available fixtures; the test SHAPE (POST, body, expected status) is what matters.
- **`get_redis_pool` dependency:** referenced as the ARQ pool dependency in Task 4 and Task 6. The implementer should use whichever existing pattern the project uses to enqueue ARQ jobs from a FastAPI route — `chat_viewmodel.py:61` is the reference implementation.
