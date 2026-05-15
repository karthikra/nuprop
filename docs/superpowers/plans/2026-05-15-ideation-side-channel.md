# Ideation Side-Channel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only Claude side-channel attached to every proposal — a sliding drawer where the agency owner can think out loud with Claude (Sonnet 4.6, prompt-cached) about a proposal without modifying its main pipeline state.

**Architecture:** One additive `channel` column on `chat_messages` (default `"main"`); a new `IdeationService.run_ideation` worker phase that reads the proposal's existing main-channel data, calls Bedrock with the proposal as a cached system prompt, and persists the assistant reply with `channel="ideation"`. Two new API endpoints under `/chat/{id}/ideation/*`. A frontend drawer that opens from the right and routes WS messages to a separate state slice by their `channel` field.

**Tech Stack:** FastAPI, async SQLAlchemy, Alembic, ARQ (Redis task queue), `redis.asyncio` (pub/sub), pytest + pytest-asyncio, Anthropic SDK via `AsyncAnthropicBedrock`, React + Vite + Zustand + Vitest + MSW.

**Spec:** `docs/superpowers/specs/2026-05-15-ideation-side-channel-design.md`

---

## File Structure

**New files:**
- `backend/alembic/versions/02_ideation_channel.py` — Alembic migration adding `chat_messages.channel` + index.
- `backend/app/services/ideation_service.py` — `IdeationService` class + `_build_ideation_system_prompt` helper.
- `backend/tests/integration/test_ideation_prompt.py` — pure-Python tests for `_build_ideation_system_prompt`.
- `backend/tests/integration/test_ideation_service.py` — `IdeationService.run_ideation` happy/failure path tests.
- `backend/tests/integration/test_ideation_api.py` — chat API tests for the two `/ideation/*` endpoints.
- `frontend/src/api/__tests__/ideation.test.ts` — Vitest tests for the two new TanStack hooks.
- `frontend/src/components/chat/ideation-drawer.tsx` — drawer component.
- `frontend/src/components/chat/ideate-button.tsx` — header button + URL-hash sync.
- `frontend/src/components/chat/__tests__/ideation-drawer.test.tsx` — drawer behaviour tests.
- `frontend/src/components/chat/__tests__/ideate-button.test.tsx` — button + hash tests.

**Modified files:**
- `backend/app/infrastructure/db/models/chat_message.py` — add `channel` column.
- `backend/app/domain/schemas/chat_schemas.py` — add `channel: str` to `ChatMessageResponse`.
- `backend/app/infrastructure/db/repositories/chat_message_repo.py` — add `channel` kwarg to `list_by_proposal` + accept it in `create`.
- `backend/app/workers/pipeline.py` — register `run_ideation` task and a separate `_run_ideation_phase` shim that does **not** touch `pipeline_state`.
- `backend/app/viewmodels/chat_viewmodel.py` — add `get_ideation_messages` and `send_ideation_message`.
- `backend/app/views/v1/chat.py` — add `GET /chat/{id}/ideation/messages` and `POST /chat/{id}/ideation/send`.
- `frontend/src/types/proposal.ts` — add optional `channel?: string` to `ChatMessage`.
- `frontend/src/stores/chat-store.ts` — add `ideationMessages` slice + route incoming `new_message` events by channel.
- `frontend/src/api/proposals.ts` — add `useIdeationMessages` and `useSendIdeationMessage` hooks.
- `frontend/src/pages/proposals/builder.tsx` — mount `<IdeateButton />` and `<IdeationDrawer />` on the proposal page.

---

## Task 1: Add `channel` column to `ChatMessage`

**Files:**
- Modify: `backend/app/infrastructure/db/models/chat_message.py`
- Create: `backend/alembic/versions/02_ideation_channel.py`

- [ ] **Step 1: Add the column to the model**

In `backend/app/infrastructure/db/models/chat_message.py`, inside `class ChatMessage(BaseModel):`, add after the `phase` line:

```python
    channel: Mapped[str] = mapped_column(
        String(20),
        default="main",
        server_default="main",
        nullable=False,
    )
```

- [ ] **Step 2: Write the Alembic migration**

Create `backend/alembic/versions/02_ideation_channel.py`:

```python
"""add channel column + index to chat_messages

Revision ID: 02_ideation_channel
Revises: 5d95cb487ab3
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "02_ideation_channel"
down_revision = "5d95cb487ab3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column(
            "channel",
            sa.String(length=20),
            server_default="main",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_messages_proposal_channel_created",
        "chat_messages",
        ["proposal_id", "channel", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_messages_proposal_channel_created",
        table_name="chat_messages",
    )
    op.drop_column("chat_messages", "channel")
```

- [ ] **Step 3: Verify the model imports and the migration is syntactically valid**

Run:
```bash
cd backend && .venv/bin/python -c "from app.infrastructure.db.models.chat_message import ChatMessage; print('cols:', [c.name for c in ChatMessage.__table__.columns])"
.venv/bin/python -m py_compile alembic/versions/02_ideation_channel.py
```
Expected: `cols:` list contains `'channel'`; `py_compile` exits 0.

- [ ] **Step 4: Verify the test schema picks up the new column**

The test suite uses `Base.metadata.create_all` (not Alembic) so the model change alone is enough. Smoke test by running one repo-touching test:

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_api.py::test_get_messages_empty -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/models/chat_message.py backend/alembic/versions/02_ideation_channel.py
git commit -m "feat: add chat_messages.channel column for ideation side-channel"
```

---

## Task 2: Repository accepts the `channel` filter and kwarg

**Files:**
- Modify: `backend/app/infrastructure/db/repositories/chat_message_repo.py`
- Test: `backend/tests/integration/test_ideation_api.py` (new file — first repo-only test goes here)

- [ ] **Step 1: Write the failing repo test**

Create `backend/tests/integration/test_ideation_api.py`:

```python
"""Integration tests for the ideation side-channel.

Repo-level tests live here too because the channel filter is what backs the
ideation API; one file per feature keeps the test surface easy to find.
"""

from __future__ import annotations

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository


async def _make_proposal(db):
    agency = await AgencyRepository(db).create(name="ID Agency", slug="id-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="P",
        brief={}, pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return proposal


async def test_list_by_proposal_filters_by_channel(db):
    proposal = await _make_proposal(db)
    msg_repo = ChatMessageRepository(db)

    await msg_repo.create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="main msg", phase="brief", channel="main",
    )
    await msg_repo.create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="ideation msg", phase="ideation", channel="ideation",
    )
    await db.commit()

    main = await msg_repo.list_by_proposal(proposal.id)
    ideation = await msg_repo.list_by_proposal(proposal.id, channel="ideation")

    assert [m.content for m in main] == ["main msg"]
    assert [m.content for m in ideation] == ["ideation msg"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_api.py::test_list_by_proposal_filters_by_channel -v`
Expected: FAIL — `TypeError: ChatMessageRepository.create() got an unexpected keyword argument 'channel'` **or** the assertion fails because both messages come back from both calls (the default `channel` filter doesn't exist yet).

- [ ] **Step 3: Read the current repository file**

Run: `cd backend && cat app/infrastructure/db/repositories/chat_message_repo.py | head -40`
This confirms what the existing `list_by_proposal` signature looks like.

- [ ] **Step 4: Add the channel filter and kwarg passthrough**

In `backend/app/infrastructure/db/repositories/chat_message_repo.py`, update `list_by_proposal` to accept a `channel` kwarg defaulting to `"main"` and add it to the `where()` clause:

```python
async def list_by_proposal(
    self,
    proposal_id,
    skip: int = 0,
    limit: int = 200,
    channel: str = "main",
):
    result = await self.session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.proposal_id == _coerce_id(proposal_id),
            ChatMessage.channel == channel,
        )
        .order_by(ChatMessage.created_at.asc())
        .offset(skip).limit(limit)
    )
    return list(result.scalars().all())
```

Notes:
- Match the imports / helpers actually used in the file. If `_coerce_id` is imported from elsewhere or absent, follow the file's existing pattern (other queries in the file). The point is to add the `channel == channel` predicate exactly once and to thread the kwarg through.
- `BaseRepository.create(**data)` (inherited) already forwards arbitrary kwargs to the SQLAlchemy model constructor, so no override of `create` is required — passing `channel="ideation"` from callers works out of the box. Verify this in Step 5.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_api.py::test_list_by_proposal_filters_by_channel -v`
Expected: PASS.

- [ ] **Step 6: Run the existing chat test to confirm no regression on the default-channel path**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_api.py -q`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/db/repositories/chat_message_repo.py backend/tests/integration/test_ideation_api.py
git commit -m "feat: ChatMessageRepository.list_by_proposal filters by channel"
```

---

## Task 3: Expose `channel` in the Pydantic response schema

**Files:**
- Modify: `backend/app/domain/schemas/chat_schemas.py`

- [ ] **Step 1: Read the current schema**

Run: `cd backend && cat app/domain/schemas/chat_schemas.py`
Note the existing `ChatMessageResponse` fields.

- [ ] **Step 2: Add `channel: str` to `ChatMessageResponse`**

In `ChatMessageResponse`, add the field (place it after `phase` for logical grouping):

```python
    channel: str = "main"
```

Default value `"main"` keeps the schema backwards-compatible for any path that builds a response from a dict that doesn't include the field. `model_validate(orm_msg)` will pick up the column from the SQLAlchemy model.

- [ ] **Step 3: Verify the field appears in API responses**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_api.py::test_send_message_brief_phase_enqueues_analyze_brief -v`
Expected: PASS (unchanged). The new field doesn't break existing assertions; it just appears in the response JSON with value `"main"`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/domain/schemas/chat_schemas.py
git commit -m "feat: ChatMessageResponse exposes the channel field"
```

---

## Task 4: `_build_ideation_system_prompt` pure function

**Files:**
- Create: `backend/app/services/ideation_service.py` (just the helper + a skeleton class for now)
- Create: `backend/tests/integration/test_ideation_prompt.py`

- [ ] **Step 1: Write the failing tests for the prompt builder**

Create `backend/tests/integration/test_ideation_prompt.py`:

```python
"""Unit tests for the ideation system-prompt builder."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.ideation_service import _build_ideation_system_prompt


def _proposal(**overrides):
    base = dict(
        project_name="Pepsi Global Dashboard",
        brief={},
        research=None,
        benchmarks=None,
        cost_model=None,
        covering_letter=None,
        executive_summary=None,
        pipeline_state={"current_phase": "brief"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_empty_proposal_states_brief_is_not_yet_established():
    prompt = _build_ideation_system_prompt(_proposal())
    assert "Project name:" in prompt and "Pepsi Global Dashboard" in prompt
    assert "Current phase:" in prompt and "brief" in prompt
    assert "Brief: Not yet established" in prompt
    # No reference to research / cost model when those fields are absent.
    assert "Research findings" not in prompt
    assert "Cost model" not in prompt
    assert "Covering letter" not in prompt


def test_full_proposal_includes_each_known_section():
    p = _proposal(
        brief={"client": {"name": "Pepsi Global"}},
        research="## Pepsi Global research\nLong paragraph " + "x" * 5000,
        benchmarks="## Benchmarks\nLong paragraph " + "y" * 3000,
        cost_model={"grand_total": 1480000, "line_items": [{}] * 6},
        covering_letter="Dear Pepsi team," + " z" * 2000,
        executive_summary="Summary " + " w" * 2000,
        pipeline_state={"current_phase": "narrative_review"},
    )
    prompt = _build_ideation_system_prompt(p)
    assert "Pepsi Global" in prompt
    assert "Research findings" in prompt
    assert "Market benchmarks" in prompt
    assert "Total ₹14,80,000" in prompt
    assert "6 line items" in prompt
    assert "Covering letter" in prompt
    assert "Executive summary" in prompt


def test_long_fields_are_truncated_with_a_marker():
    p = _proposal(research="a" * 10000)
    prompt = _build_ideation_system_prompt(p)
    assert "... (truncated)" in prompt
    # The truncated body must be present but bounded.
    research_idx = prompt.index("Research findings")
    assert prompt.count("a", research_idx) <= 3100  # 3000 cap + a little slack


def test_preamble_describes_the_read_only_invariant():
    prompt = _build_ideation_system_prompt(_proposal())
    assert "ideation copilot" in prompt
    assert "cannot modify" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.ideation_service`.

- [ ] **Step 3: Write the prompt-builder module**

Create `backend/app/services/ideation_service.py`:

```python
"""The proposal ideation side-channel.

A read-only Claude side-channel attached to each proposal. The user opens it
to think out loud about strategy / angles / pricing without polluting the
main pipeline. Nothing here mutates ``proposal.*`` fields; the only writes
are to ``chat_messages`` with ``channel="ideation"``.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_IDEATION_SYSTEM_PREAMBLE = """\
You are NUPROP's ideation copilot — a thinking partner for a senior BD lead
at a design / professional-services agency.

The user has an open proposal and wants to think out loud with you about it.
You should:
- Ask probing questions, suggest angles, surface assumptions.
- Reference what's already known about this proposal (below) when helpful.
- Be honest about trade-offs, not just agreeable.
- Keep responses tight and conversational — this is a brainstorm, not a deck.
- Never fabricate facts; if you don't know something, say so.

You can see what the agency has produced so far, but you cannot modify it.
If the user wants to apply your suggestions, they'll do that themselves in
the main proposal flow.
"""


# Truncation cutoffs (characters, first-pass heuristics — tune via real usage).
_RESEARCH_CHARS = 3000
_BENCHMARKS_CHARS = 2000
_LETTER_CHARS = 1500
_SUMMARY_CHARS = 1500


def _truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars`` with a visible marker if cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... (truncated)"


def _build_ideation_system_prompt(proposal) -> str:
    """Assemble the system prompt for one ideation turn.

    Gracefully handles a brand-new proposal where ``brief`` is empty and
    ``research`` / narrative fields are ``None``. Long text fields are
    truncated so the prompt stays bounded even for a fully-built proposal.
    """
    parts: list[str] = [_IDEATION_SYSTEM_PREAMBLE, "## What's known about this proposal so far\n"]

    parts.append(f"**Project name:** {proposal.project_name}")
    parts.append(
        f"**Current phase:** {(proposal.pipeline_state or {}).get('current_phase', 'brief')}"
    )

    if proposal.brief:
        parts.append(
            f"\n**Brief:**\n```json\n{json.dumps(proposal.brief, indent=2, ensure_ascii=False)}\n```"
        )
    else:
        parts.append("\n**Brief:** Not yet established — the user hasn't completed brief intake.")

    if proposal.research:
        parts.append(f"\n**Research findings:**\n{_truncate(proposal.research, _RESEARCH_CHARS)}")
    if proposal.benchmarks:
        parts.append(f"\n**Market benchmarks:**\n{_truncate(proposal.benchmarks, _BENCHMARKS_CHARS)}")

    if proposal.cost_model:
        cm = proposal.cost_model
        total = cm.get("grand_total", 0)
        items = len(cm.get("line_items", []))
        # ₹ formatting follows Indian numbering grouping (1,00,000 = 1 lakh).
        parts.append(f"\n**Cost model:** Total ₹{_inr(total)}, {items} line items.")

    if proposal.covering_letter:
        parts.append(
            f"\n**Covering letter (current draft):**\n{_truncate(proposal.covering_letter, _LETTER_CHARS)}"
        )
    if proposal.executive_summary:
        parts.append(
            f"\n**Executive summary:**\n{_truncate(proposal.executive_summary, _SUMMARY_CHARS)}"
        )

    return "\n".join(parts)


def _inr(amount: int) -> str:
    """Format an integer rupee amount with Indian numbering (1,00,000 style)."""
    s = str(int(amount))
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    groups: list[str] = []
    while len(rest) > 2:
        groups.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.append(rest)
    return ",".join(reversed(groups)) + "," + last3


class IdeationService:
    """Worker-side runner for the ideation phase. Filled in by the next task."""

    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis

    async def run_ideation(self, proposal_id: UUID | str) -> None:
        raise NotImplementedError  # implemented in Task 5
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_prompt.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ideation_service.py backend/tests/integration/test_ideation_prompt.py
git commit -m "feat: _build_ideation_system_prompt — read-only proposal context for the side-channel"
```

---

## Task 5: `IdeationService.run_ideation` happy path

**Files:**
- Modify: `backend/app/services/ideation_service.py`
- Create: `backend/tests/integration/test_ideation_service.py`

- [ ] **Step 1: Write the failing tests for `run_ideation`**

Create `backend/tests/integration/test_ideation_service.py`:

```python
"""Integration tests for IdeationService.run_ideation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.models.chat_message import MessageRole
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.ideation_service import IdeationService


async def _make_proposal(db, *, brief=None):
    agency = await AgencyRepository(db).create(name="ID Agency", slug="id-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="Ideation Project",
        brief=brief or {},
        pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return agency, client, proposal


def _bedrock_reply(text: str):
    """Build the minimal anthropic-SDK response shape IdeationService consumes."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


async def test_run_ideation_persists_assistant_msg_on_ideation_channel(db, monkeypatch):
    _, _, proposal = await _make_proposal(db)
    pid = proposal.id

    # Seed a user message on the ideation channel so the service has chat history to send.
    msg_repo = ChatMessageRepository(db)
    await msg_repo.create(
        proposal_id=pid, role=MessageRole.USER.value, message_type="text",
        content="What angle should we lead with?", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(return_value=_bedrock_reply("Try angle X because Y."))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(pid)

    # The assistant reply is in the DB on the ideation channel, committed.
    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(pid, channel="ideation")
        roles_and_content = [(m.role, m.content) for m in msgs]
        assert ("assistant", "Try angle X because Y.") in roles_and_content
        # User message is still there.
        assert any(r == "user" and c.startswith("What angle") for r, c in roles_and_content)

    # The main channel was not touched.
    async with async_session_factory() as fresh:
        main = await ChatMessageRepository(fresh).list_by_proposal(pid)
        assert main == []  # default channel is "main"; the ideation msgs don't leak in


async def test_run_ideation_passes_cache_control_system_block_to_bedrock(db, monkeypatch):
    _, _, proposal = await _make_proposal(db, brief={"client": {"name": "Acme"}})
    await ChatMessageRepository(db).create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="ping", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(return_value=_bedrock_reply("pong"))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(proposal.id)

    kwargs = fake_create.await_args.kwargs
    # System block is a list (not a bare string) and carries cache_control.
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Cached prompt mentions the read-only invariant + the project name.
    assert "ideation copilot" in kwargs["system"][0]["text"]
    assert "Ideation Project" in kwargs["system"][0]["text"]
    # Messages are the ideation channel history, not the (empty) main one.
    assert kwargs["messages"] == [{"role": "user", "content": "ping"}]


async def test_run_ideation_does_not_mutate_proposal_fields(db, monkeypatch):
    """The read-only invariant: nothing on ``proposal.*`` changes."""
    _, _, proposal = await _make_proposal(db, brief={"client": {"name": "Acme"}})
    pid = proposal.id
    await ChatMessageRepository(db).create(
        proposal_id=pid, role="user", message_type="text",
        content="hi", phase="ideation", channel="ideation",
    )
    await db.commit()

    before = (proposal.brief, proposal.research, proposal.cost_model,
              proposal.covering_letter, proposal.pipeline_state)

    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(AsyncMock(return_value=_bedrock_reply("ok"))),
    )

    await IdeationService(db, AsyncMock()).run_ideation(pid)

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        after = (refetched.brief, refetched.research, refetched.cost_model,
                 refetched.covering_letter, refetched.pipeline_state)
    assert before == after, "ideation must not mutate proposal fields"


class _StubAI:
    """Bare-bones stand-in for AIService used by run_ideation."""

    def __init__(self, messages_create):
        self.messages_create = messages_create

    def model_for(self, tier):
        return "global.anthropic.claude-sonnet-4-6"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_service.py -v`
Expected: FAIL — `NotImplementedError` raised by the skeleton from Task 4.

- [ ] **Step 3: Implement `run_ideation`**

In `backend/app/services/ideation_service.py`, replace the skeleton class with the full version. Also add the imports it needs at the top of the file (alongside what's already there):

```python
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.services.llm import Tier, get_ai_service
```

Then replace the placeholder class:

```python
class IdeationService:
    """Worker-side runner for the ideation phase.

    Read-only by construction: this class does NOT call
    ``ProposalRepository.update`` or write to any ``proposal.*`` field. The
    only writes it performs are to ``chat_messages`` with
    ``channel="ideation"``.
    """

    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis
        self.proposal_repo = ProposalRepository(session)
        self.msg_repo = ChatMessageRepository(session)
        self.ai = get_ai_service()

    async def run_ideation(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            logger.warning("run_ideation: proposal %s not found", proposal_id)
            return

        history = await self.msg_repo.list_by_proposal(
            proposal_id, channel="ideation", limit=200,
        )
        messages = [
            {"role": m.role, "content": m.content}
            for m in history
            if m.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
        ]

        system_text = _build_ideation_system_prompt(proposal)
        response = await self.ai.messages_create(
            model=self.ai.model_for(Tier.BALANCED),
            max_tokens=2048,
            temperature=0.7,
            system=[{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )
        response_text = response.content[0].text

        assistant_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value,
            content=response_text,
            phase="ideation",
            channel="ideation",
        )
        await self.session.commit()  # commit BEFORE broadcast
        await self._emit_message(proposal_id, assistant_msg)

    async def _emit_message(self, proposal_id, msg) -> None:
        await publish(
            self.redis,
            str(proposal_id),
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
            },
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_service.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ideation_service.py backend/tests/integration/test_ideation_service.py
git commit -m "feat: IdeationService.run_ideation — Sonnet 4.6 + cache_control + ideation-channel commit"
```

---

## Task 6: `IdeationService` failure path — write error message instead of touching `pipeline_state`

**Files:**
- Modify: `backend/app/services/ideation_service.py`
- Modify: `backend/tests/integration/test_ideation_service.py`

The worker-task wrapper is what actually catches the exception (Task 7). In this task we only ensure `IdeationService.run_ideation` propagates the exception cleanly — the wrapper turns it into a chat-message error block.

- [ ] **Step 1: Append the failure-propagation test**

Append to `backend/tests/integration/test_ideation_service.py`:

```python
async def test_run_ideation_propagates_bedrock_errors(db, monkeypatch):
    """Bedrock failures should bubble out of run_ideation so the worker wrapper
    can record an error message — the service itself doesn't swallow them."""
    _, _, proposal = await _make_proposal(db)
    await ChatMessageRepository(db).create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="hi", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(side_effect=RuntimeError("bedrock down"))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    with pytest.raises(RuntimeError, match="bedrock down"):
        await IdeationService(db, AsyncMock()).run_ideation(proposal.id)

    # No assistant message was persisted on failure.
    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(
            proposal.id, channel="ideation",
        )
        assert not any(m.role == "assistant" for m in msgs)
```

- [ ] **Step 2: Run the test to verify it passes (no code change needed yet)**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_service.py::test_run_ideation_propagates_bedrock_errors -v`
Expected: PASS. The service has no try/except, so exceptions naturally propagate; the test simply locks that contract in.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_ideation_service.py
git commit -m "test: IdeationService propagates Bedrock errors instead of swallowing"
```

---

## Task 7: Worker task wrapper for ideation

**Files:**
- Modify: `backend/app/workers/pipeline.py`
- Create test in: `backend/tests/integration/test_ideation_worker.py`

The wrapper differs from the main pipeline's `_run_phase` in one crucial way: on
failure, it writes an error message to the ideation channel instead of touching
`proposal.pipeline_state`. This preserves the isolation invariant.

- [ ] **Step 1: Write the failing worker tests**

Create `backend/tests/integration/test_ideation_worker.py`:

```python
"""Tests for the run_ideation ARQ task wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.workers import pipeline as worker


async def _make_proposal(db):
    agency = await AgencyRepository(db).create(name="IW Agency", slug="iw-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="IW Project",
        brief={},
        pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return proposal


def _ctx():
    return {"redis": AsyncMock(), "job_try": 1}


async def test_run_ideation_task_does_not_touch_pipeline_state(db, monkeypatch):
    proposal = await _make_proposal(db)
    pid = str(proposal.id)
    pipeline_state_before = dict(proposal.pipeline_state)

    # Stub IdeationService so we don't need real Bedrock.
    from app.services import ideation_service as ide_mod

    async def fake_run_ideation(self, proposal_id):  # noqa: ARG001
        return None

    monkeypatch.setattr(ide_mod.IdeationService, "run_ideation", fake_run_ideation)

    await worker.run_ideation(_ctx(), pid)

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
    assert refetched.pipeline_state == pipeline_state_before, (
        "ideation must not write job_status or anything else into pipeline_state"
    )


async def test_run_ideation_task_records_error_message_on_failure(db, monkeypatch):
    proposal = await _make_proposal(db)
    pid = str(proposal.id)
    pipeline_state_before = dict(proposal.pipeline_state)

    from app.services import ideation_service as ide_mod

    async def boom(self, proposal_id):  # noqa: ARG001
        raise RuntimeError("bedrock unreachable")

    monkeypatch.setattr(ide_mod.IdeationService, "run_ideation", boom)

    await worker.run_ideation(_ctx(), pid)  # must NOT raise

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(
            pid, channel="ideation",
        )
        error_msgs = [m for m in msgs if (m.extra_data or {}).get("kind") == "error"]
        assert error_msgs, "expected an error chat message on the ideation channel"
        assert error_msgs[0].role == "system"
        assert "bedrock unreachable" in error_msgs[0].content

        refetched = await ProposalRepository(fresh).get_by_id(pid)
    assert refetched.pipeline_state == pipeline_state_before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_worker.py -v`
Expected: FAIL — `AttributeError: module 'app.workers.pipeline' has no attribute 'run_ideation'`.

- [ ] **Step 3: Add the wrapper + register it on the worker**

In `backend/app/workers/pipeline.py`, add a new shim alongside `_run_phase`:

```python
async def _run_ideation_phase(ctx: dict, proposal_id: str) -> None:
    """Run an ideation turn. Isolated from the main pipeline:

    * Does NOT update ``proposal.pipeline_state`` — ideation has no job_status.
    * On failure, writes a single error message to the ideation channel and
      returns cleanly (ARQ marks the job done). The user re-prompts to retry.
    """
    from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
    from app.services.ideation_service import IdeationService

    try:
        async with async_session_factory() as session:
            await IdeationService(session, ctx["redis"]).run_ideation(proposal_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ideation phase failed for %s", proposal_id)
        async with async_session_factory() as session:
            await ChatMessageRepository(session).create(
                proposal_id=proposal_id,
                role="system",
                message_type="text",
                content=f"Couldn't reach Bedrock — {exc}. Send another message to try again.",
                extra_data={"kind": "error", "error": str(exc)},
                phase="ideation",
                channel="ideation",
            )
            await session.commit()
        await publish(ctx["redis"], proposal_id, {
            "type": "pipeline_error",
            "phase": "run_ideation",
            "error": str(exc),
        })


async def run_ideation(ctx: dict, proposal_id: str) -> None:
    await _run_ideation_phase(ctx, proposal_id)
```

Add `run_ideation` to `WorkerSettings.functions`:

```python
class WorkerSettings:
    functions = [
        analyze_brief, run_research, run_benchmarks,
        build_cost_model, generate_narrative, generate_outputs,
        run_ideation,                                  # NEW
    ]
    redis_settings = get_redis_settings()
    max_tries = ARQ_MAX_TRIES
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_worker.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Confirm the existing worker suite still passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_pipeline_worker.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/pipeline.py backend/tests/integration/test_ideation_worker.py
git commit -m "feat: run_ideation worker task with isolated failure handling"
```

---

## Task 8: `ChatViewModel.get_ideation_messages` + `send_ideation_message`

**Files:**
- Modify: `backend/app/viewmodels/chat_viewmodel.py`

- [ ] **Step 1: Read current ChatViewModel structure**

Run: `cd backend && grep -n "async def\|@property" app/viewmodels/chat_viewmodel.py`
Confirms where to slot the two new methods.

- [ ] **Step 2: Add the methods**

Append the following two methods to `ChatViewModel` in `backend/app/viewmodels/chat_viewmodel.py` (a good place is right after `get_messages` so the read-only one sits next to its sibling, with `send_ideation_message` after `send_message`):

```python
    async def get_ideation_messages(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        skip: int = 0,
        limit: int = 200,
    ) -> list[ChatMessage] | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None
        return await self.msg_repo.list_by_proposal(
            proposal_id, skip, limit, channel="ideation",
        )

    async def send_ideation_message(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        content: str,
    ) -> list[ChatMessage] | None:
        """Persist the user message on the ideation channel and enqueue
        run_ideation. Returns just the user message — the assistant reply
        arrives over the WebSocket."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        user_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.USER.value,
            message_type=MessageType.TEXT.value,
            content=content,
            phase="ideation",
            channel="ideation",
        )
        await self._broadcast_msg(proposal_id, user_msg)
        await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})

        # Per-turn idempotency: each user message is a fresh ideation run.
        await self._enqueue(
            "run_ideation", proposal_id, idempotency_key=str(user_msg.id),
        )
        self.status_code = 201
        return [user_msg]
```

Notes:
- `MessageRole`, `MessageType`, `ws_manager`, `ChatMessage` are already imported at the top of the file. If your shadow of the file is different from this assumption, add only what's missing — don't duplicate imports.

- [ ] **Step 3: Smoke-import to verify the file still loads**

Run: `cd backend && .venv/bin/python -c "from app.viewmodels.chat_viewmodel import ChatViewModel; m=ChatViewModel; print('ok', [a for a in dir(m) if 'ideation' in a])"`
Expected: prints `ok ['get_ideation_messages', 'send_ideation_message']`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/viewmodels/chat_viewmodel.py
git commit -m "feat: ChatViewModel.get_ideation_messages and send_ideation_message"
```

---

## Task 9: API routes — `GET /chat/{id}/ideation/messages` and `POST /chat/{id}/ideation/send`

**Files:**
- Modify: `backend/app/views/v1/chat.py`
- Modify: `backend/tests/integration/test_ideation_api.py`

- [ ] **Step 1: Append the API tests**

Append to `backend/tests/integration/test_ideation_api.py`:

```python
import json  # add at the top of the file if not already there


async def _client_proposal_via_api(http, headers):
    c = (await http.post("/api/v1/clients", headers=headers, json={"name": "Ideation Client"})).json()
    p = (await http.post(
        "/api/v1/proposals", headers=headers,
        json={"client_id": c["id"], "project_name": "Ideation Project"},
    )).json()
    return p


async def test_get_ideation_messages_returns_empty_for_new_proposal(client, registered):
    p = await _client_proposal_via_api(client, registered.headers)
    resp = await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=registered.headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_ideation_messages_cross_agency_returns_404(client, registered, second_agency):
    p = await _client_proposal_via_api(client, registered.headers)
    resp = await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=second_agency.headers,
    )
    assert resp.status_code == 404


async def test_send_ideation_enqueues_and_returns_only_the_user_message(
    client, registered, arq_pool,
):
    p = await _client_proposal_via_api(client, registered.headers)
    resp = await client.post(
        f"/api/v1/chat/{p['id']}/ideation/send",
        headers=registered.headers,
        json={"content": "What if we positioned this as a retainer?"},
    )
    assert resp.status_code == 201
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["channel"] == "ideation"
    assert msgs[0]["content"].startswith("What if")

    arq_pool.enqueue_job.assert_awaited()
    job_name = arq_pool.enqueue_job.await_args.args[0]
    assert job_name == "run_ideation"


async def test_ideation_thread_is_separate_from_the_main_thread(
    client, registered, arq_pool,
):
    """Posting on the ideation channel must NOT pollute the main thread."""
    p = await _client_proposal_via_api(client, registered.headers)

    await client.post(
        f"/api/v1/chat/{p['id']}/ideation/send",
        headers=registered.headers,
        json={"content": "ideation only"},
    )

    main = (await client.get(
        f"/api/v1/chat/{p['id']}/messages",
        headers=registered.headers,
    )).json()
    assert main == []

    ideation = (await client.get(
        f"/api/v1/chat/{p['id']}/ideation/messages",
        headers=registered.headers,
    )).json()
    assert len(ideation) == 1
    assert ideation[0]["channel"] == "ideation"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_api.py -v`
Expected: FAIL — `404 Not Found` for the new URL routes.

- [ ] **Step 3: Add the two routes to chat.py**

In `backend/app/views/v1/chat.py`, add after the existing `send_message` route (and reusing the `SendMessageRequest` body already imported in this file):

```python
@router.get(
    "/{proposal_id}/ideation/messages",
    response_model=list[ChatMessageResponse],
)
async def get_ideation_messages(
    proposal_id: UUID,
    skip: int = 0,
    limit: int = 200,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    messages = await vm.get_ideation_messages(proposal_id, agency_id, skip, limit)
    if messages is None:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return messages


@router.post(
    "/{proposal_id}/ideation/send",
    response_model=list[ChatMessageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def send_ideation_message(
    proposal_id: UUID,
    body: SendMessageRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    """Persist the user message on the ideation channel and enqueue the
    run_ideation worker job. Returns just the user message — the assistant
    reply arrives via WebSocket."""
    result = await vm.send_ideation_message(proposal_id, agency_id, body.content)
    if result is None:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return [ChatMessageResponse.model_validate(m) for m in result]
```

- [ ] **Step 4: Verify it compiles and the route count went up by 2**

Run: `cd backend && .venv/bin/python -m py_compile app/views/v1/chat.py && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"`
Expected: prints `routes: 64` (previously 62, +2 for the new endpoints).

- [ ] **Step 5: Run the API tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_ideation_api.py -v`
Expected: all PASS (5 tests counting the repo test from Task 2).

- [ ] **Step 6: Confirm the full backend suite is still green**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all PASS, 0 skipped.

- [ ] **Step 7: Commit**

```bash
git add backend/app/views/v1/chat.py backend/tests/integration/test_ideation_api.py
git commit -m "feat: GET /chat/{id}/ideation/messages and POST /chat/{id}/ideation/send"
```

---

## Task 10: Frontend `ChatMessage` type carries `channel`

**Files:**
- Modify: `frontend/src/types/proposal.ts`

- [ ] **Step 1: Read the type and locate `ChatMessage`**

Run: `cd frontend && grep -n "ChatMessage\|channel" src/types/proposal.ts | head`
Confirms the surrounding shape.

- [ ] **Step 2: Add the channel field**

In `frontend/src/types/proposal.ts`, inside the `ChatMessage` interface, add:

```typescript
  /** "main" (default) or "ideation". Backend always returns one of these. */
  channel: string
```

If TypeScript flags existing fixtures missing the field, add the literal default `channel: 'main'` to the failing fixtures.

- [ ] **Step 3: Verify the type-check passes**

Run: `cd frontend && pnpm exec tsc -b 2>&1 | tail -20`
Expected: 0 errors. If TS errors appear in test fixtures (`*.test.tsx` mock messages missing `channel`), add `channel: 'main'` to those fixtures.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/proposal.ts frontend/src/**/*.test.tsx
git commit -m "feat(types): ChatMessage carries the channel field"
```

---

## Task 11: Chat store routes incoming WS messages by `channel`

**Files:**
- Modify: `frontend/src/stores/chat-store.ts`
- Test: existing `frontend/src/stores/__tests__/chat-store.test.ts` (or create if absent — see Step 1)

- [ ] **Step 1: Locate the existing store and tests**

Run:
```bash
cd frontend && ls src/stores/__tests__/ 2>/dev/null
grep -n "messages\|addMessage\|new_message\|channel" src/stores/chat-store.ts | head -30
```

If `src/stores/__tests__/chat-store.test.ts` doesn't exist, create it with the test below. If it does, append the new test to it.

- [ ] **Step 2: Write the failing test**

Add to `frontend/src/stores/__tests__/chat-store.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '../chat-store'
import type { ChatMessage } from '../../types/proposal'

function mainMsg(id: string): ChatMessage {
  return {
    id, proposal_id: 'p1', role: 'assistant', message_type: 'text',
    content: 'main', extra_data: {}, phase: 'brief', created_at: 't',
    channel: 'main',
  }
}

function ideationMsg(id: string): ChatMessage {
  return { ...mainMsg(id), content: 'ideation', channel: 'ideation' }
}

describe('chat-store channel routing', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('addMessage with channel=main lands in messages, not ideationMessages', () => {
    useChatStore.getState().addMessage(mainMsg('m1'))
    expect(useChatStore.getState().messages.map(m => m.id)).toEqual(['m1'])
    expect(useChatStore.getState().ideationMessages).toEqual([])
  })

  it('addMessage with channel=ideation lands in ideationMessages, not messages', () => {
    useChatStore.getState().addMessage(ideationMsg('i1'))
    expect(useChatStore.getState().ideationMessages.map(m => m.id)).toEqual(['i1'])
    expect(useChatStore.getState().messages).toEqual([])
  })

  it('dedupes by id within each channel independently', () => {
    useChatStore.getState().addMessage(mainMsg('m1'))
    useChatStore.getState().addMessage(mainMsg('m1'))
    useChatStore.getState().addMessage(ideationMsg('m1'))   // same id, different channel
    expect(useChatStore.getState().messages.length).toBe(1)
    expect(useChatStore.getState().ideationMessages.length).toBe(1)
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/stores/__tests__/chat-store.test.ts`
Expected: FAIL — `useChatStore.getState().ideationMessages` is `undefined` (no slice yet).

- [ ] **Step 4: Add the ideation slice + channel routing**

In `frontend/src/stores/chat-store.ts`:

1. Extend the state type with a new field next to `messages`:

```typescript
ideationMessages: ChatMessage[]
```

2. Initialize it to `[]` in `create<ChatState>((set, get) => ({ ... }))`.

3. Update `addMessage` to route by `channel`:

```typescript
addMessage: (msg: ChatMessage) => {
  const target = msg.channel === 'ideation' ? 'ideationMessages' : 'messages'
  set((state) => {
    const existing = state[target] as ChatMessage[]
    if (existing.some((m) => m.id === msg.id)) return {}
    return { [target]: [...existing, msg] } as Partial<ChatState>
  })
},
```

4. Update `reset` to clear both slices.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/stores/__tests__/chat-store.test.ts`
Expected: 3 PASS.

- [ ] **Step 6: Confirm the rest of the frontend suite is still green**

Run: `cd frontend && pnpm test --run`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/chat-store.ts frontend/src/stores/__tests__/chat-store.test.ts
git commit -m "feat(store): route incoming chat messages by channel into separate slices"
```

---

## Task 12: API hooks `useIdeationMessages` + `useSendIdeationMessage`

**Files:**
- Modify: `frontend/src/api/proposals.ts`
- Create: `frontend/src/api/__tests__/ideation.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/__tests__/ideation.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '../../test/mocks/server'
import { API } from '../../test/mocks/handlers'
import { useIdeationMessages, useSendIdeationMessage } from '../proposals'

function queryWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('ideation hooks', () => {
  it('useIdeationMessages GETs /chat/:id/ideation/messages', async () => {
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () =>
        HttpResponse.json([
          { id: 'i1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: 'hi', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ]),
      ),
    )
    const { result } = renderHook(() => useIdeationMessages('p1'), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].channel).toBe('ideation')
  })

  it('useSendIdeationMessage POSTs to /chat/:id/ideation/send', async () => {
    let body: { content?: string } | null = null
    server.use(
      http.post(`${API}/chat/p1/ideation/send`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json([
          { id: 'u1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: body?.content ?? '', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ])
      }),
    )
    const { result } = renderHook(() => useSendIdeationMessage(), { wrapper: queryWrapper() })
    await act(async () => {
      await result.current.mutateAsync({ proposalId: 'p1', content: 'what if?' })
    })
    expect(body).toEqual({ content: 'what if?' })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/api/__tests__/ideation.test.ts`
Expected: FAIL — the two hooks don't exist yet.

- [ ] **Step 3: Add the hooks**

In `frontend/src/api/proposals.ts`, after the existing `useSendMessage` hook, append:

```typescript
export function useIdeationMessages(proposalId: string) {
  return useQuery({
    queryKey: ['ideation-messages', proposalId],
    queryFn: async () => {
      const { data } = await api.get<ChatMessage[]>(`/chat/${proposalId}/ideation/messages`)
      return data
    },
    enabled: !!proposalId,
  })
}

export function useSendIdeationMessage() {
  return useMutation({
    mutationFn: async ({ proposalId, content }: { proposalId: string; content: string }) => {
      const { data } = await api.post<ChatMessage[]>(
        `/chat/${proposalId}/ideation/send`,
        { content },
      )
      return data
    },
  })
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/api/__tests__/ideation.test.ts`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/proposals.ts frontend/src/api/__tests__/ideation.test.ts
git commit -m "feat(api): useIdeationMessages and useSendIdeationMessage hooks"
```

---

## Task 13: `<IdeationDrawer />` — empty state, message list, input, send

**Files:**
- Create: `frontend/src/components/chat/ideation-drawer.tsx`
- Create: `frontend/src/components/chat/__tests__/ideation-drawer.test.tsx`

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/chat/__tests__/ideation-drawer.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { IdeationDrawer } from '../ideation-drawer'
import { useChatStore } from '../../../stores/chat-store'

function wrap(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('IdeationDrawer', () => {
  it('shows the empty state with clickable suggestions on a fresh thread', async () => {
    useChatStore.getState().reset()
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Think out loud/i)).toBeInTheDocument()
    expect(screen.getByText(/What angle should we lead with/)).toBeInTheDocument()

    await userEvent.click(screen.getByText(/What angle should we lead with/))
    const input = screen.getByPlaceholderText(/talk to claude/i) as HTMLTextAreaElement
    expect(input.value).toContain('What angle should we lead with')
  })

  it('renders messages from the ideation slice', async () => {
    useChatStore.getState().reset()
    useChatStore.getState().addMessage({
      id: 'i1', proposal_id: 'p1', role: 'assistant', message_type: 'text',
      content: 'Try the retainer angle.', extra_data: {}, phase: 'ideation',
      created_at: '2026-01-01T00:00:00Z', channel: 'ideation',
    })
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Try the retainer angle/)).toBeInTheDocument()
  })

  it('posts the input to the send endpoint', async () => {
    useChatStore.getState().reset()
    let body: { content?: string } | null = null
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
      http.post(`${API}/chat/p1/ideation/send`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json([
          { id: 'u1', proposal_id: 'p1', role: 'user', message_type: 'text',
            content: body?.content ?? '', extra_data: {}, phase: 'ideation',
            created_at: '2026-01-01T00:00:00Z', channel: 'ideation' },
        ])
      }),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    const input = await screen.findByPlaceholderText(/talk to claude/i)
    await userEvent.type(input, 'will retainer work?')
    await userEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(body).toEqual({ content: 'will retainer work?' })
  })

  it('renders an inline error block for ideation error messages', async () => {
    useChatStore.getState().reset()
    useChatStore.getState().addMessage({
      id: 'e1', proposal_id: 'p1', role: 'system', message_type: 'text',
      content: "Couldn't reach Bedrock — bedrock down. Send another message to try again.",
      extra_data: { kind: 'error', error: 'bedrock down' },
      phase: 'ideation', created_at: '2026-01-01T00:00:00Z',
      channel: 'ideation',
    })
    server.use(
      http.get(`${API}/chat/p1/ideation/messages`, () => HttpResponse.json([])),
    )
    render(wrap(<IdeationDrawer open onClose={() => {}} proposalId="p1" />))
    expect(await screen.findByText(/Couldn't reach Bedrock/)).toBeInTheDocument()
    expect(screen.getByText(/Couldn't reach Bedrock/).closest('[data-error="ideation"]')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/ideation-drawer.test.tsx`
Expected: FAIL — `Cannot find module '../ideation-drawer'`.

- [ ] **Step 3: Implement the drawer**

Create `frontend/src/components/chat/ideation-drawer.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../stores/chat-store'
import { useIdeationMessages, useSendIdeationMessage } from '../../api/proposals'
import type { ChatMessage } from '../../types/proposal'

interface Props {
  open: boolean
  onClose: () => void
  proposalId: string
}

const SUGGESTIONS = [
  'What angle should we lead with?',
  'What would a retainer version of this look like?',
  'What objections might the client have?',
  'If we cut the budget by 30%, what would we drop?',
]

export function IdeationDrawer({ open, onClose, proposalId }: Props) {
  // Hydrate the store from the server on first open of this proposal.
  const { data: serverMsgs } = useIdeationMessages(proposalId)
  const addMessage = useChatStore((s) => s.addMessage)
  useEffect(() => {
    if (serverMsgs) {
      for (const m of serverMsgs) {
        addMessage({ ...m, channel: 'ideation' })
      }
    }
  }, [serverMsgs, addMessage])

  const messages = useChatStore((s) => s.ideationMessages)
  const send = useSendIdeationMessage()

  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Close on Esc.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Auto-scroll to bottom when messages change.
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  if (!open) return null

  const handleSend = async () => {
    const content = draft.trim()
    if (!content) return
    setDraft('')
    try {
      const created = await send.mutateAsync({ proposalId, content })
      for (const m of created) addMessage({ ...m, channel: 'ideation' })
    } catch (err) {
      console.error('ideation send failed', err)
    }
  }

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-stone-900/30 transition-opacity"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-label="Ideation"
        className="fixed right-0 top-0 bottom-0 z-50 w-full sm:w-[40vw] sm:max-w-[560px] bg-slate-50 border-l border-slate-200 flex flex-col"
      >
        <header className="border-b border-slate-200 px-5 py-4 flex items-start gap-3">
          <span aria-hidden className="text-lg">💡</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-900">Ideation</p>
            <p className="text-xs text-slate-600 leading-snug">
              Talking through this proposal with Claude. Read-only — nothing here modifies the main flow.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close ideation"
            className="text-slate-500 hover:text-slate-900"
          >
            ✕
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.length === 0 ? (
            <EmptyState
              onPick={(s) => {
                setDraft(s)
                inputRef.current?.focus()
              }}
            />
          ) : (
            messages.map((m) => <IdeationBubble key={m.id} message={m} />)
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3 flex gap-2">
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="Talk to Claude about this proposal…"
            rows={2}
            className="flex-1 resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!draft.trim() || send.isPending}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </aside>
    </>
  )
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-700 space-y-3">
      <p className="font-medium text-slate-900">💡 Think out loud about this proposal.</p>
      <p className="leading-relaxed">
        I can see everything the agency has put together so far — the brief, research,
        costing, narrative — but I won't change any of it. Use me to surface
        assumptions, try different angles, or stress-test the strategy.
      </p>
      <p className="text-xs uppercase tracking-wider text-slate-500">Try asking</p>
      <ul className="space-y-1">
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="text-left text-sm text-slate-700 hover:text-slate-900 hover:underline"
            >
              • {s}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function IdeationBubble({ message }: { message: ChatMessage }) {
  const extra = (message.extra_data ?? {}) as Record<string, unknown>
  if (extra.kind === 'error') {
    return (
      <div
        data-error="ideation"
        className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
      >
        ⚠ {message.content}
      </div>
    )
  }
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-slate-900 text-white rounded-br-md'
            : 'bg-white border border-slate-200 text-slate-800 rounded-bl-md'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/ideation-drawer.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ideation-drawer.tsx frontend/src/components/chat/__tests__/ideation-drawer.test.tsx
git commit -m "feat(ui): IdeationDrawer with empty state, message list, send, and error rendering"
```

---

## Task 14: `<IdeateButton />` + URL hash sync

**Files:**
- Create: `frontend/src/components/chat/ideate-button.tsx`
- Create: `frontend/src/components/chat/__tests__/ideate-button.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/chat/__tests__/ideate-button.test.tsx`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IdeateButton } from '../ideate-button'

describe('IdeateButton', () => {
  beforeEach(() => {
    window.location.hash = ''
  })

  it('clicks toggle the parent open prop and update the URL hash to #ideate', async () => {
    let open = false
    const setOpen = (v: boolean) => { open = v }
    const { rerender } = render(<IdeateButton open={open} onToggle={setOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /ideate/i }))
    expect(open).toBe(true)
    expect(window.location.hash).toBe('#ideate')

    rerender(<IdeateButton open={true} onToggle={setOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /ideate/i }))
    expect(open).toBe(false)
    expect(window.location.hash).toBe('')
  })

  it('honors a preexisting #ideate hash on mount', () => {
    window.location.hash = '#ideate'
    let open = false
    const setOpen = (v: boolean) => { open = v }
    render(<IdeateButton open={open} onToggle={setOpen} />)
    expect(open).toBe(true)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/ideate-button.test.tsx`
Expected: FAIL — `Cannot find module '../ideate-button'`.

- [ ] **Step 3: Implement the button**

Create `frontend/src/components/chat/ideate-button.tsx`:

```tsx
import { useEffect } from 'react'

interface Props {
  open: boolean
  onToggle: (open: boolean) => void
}

export function IdeateButton({ open, onToggle }: Props) {
  // Sync the URL hash on toggle so a refresh reopens the drawer + the URL is shareable.
  useEffect(() => {
    const target = open ? '#ideate' : ''
    if (window.location.hash !== target) {
      // Use replaceState so toggling doesn't pollute browser history.
      const url = window.location.pathname + window.location.search + target
      window.history.replaceState(null, '', url)
    }
  }, [open])

  // On mount, honor an inbound #ideate hash.
  useEffect(() => {
    if (window.location.hash === '#ideate' && !open) {
      onToggle(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <button
      type="button"
      onClick={() => onToggle(!open)}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors ${
        open
          ? 'border-slate-400 bg-slate-100 text-slate-900'
          : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
      }`}
      aria-pressed={open}
      aria-label="Ideate"
    >
      <span aria-hidden>💡</span>
      <span>Ideate</span>
    </button>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/chat/__tests__/ideate-button.test.tsx`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ideate-button.tsx frontend/src/components/chat/__tests__/ideate-button.test.tsx
git commit -m "feat(ui): IdeateButton with URL hash sync"
```

---

## Task 15: Mount the button + drawer on the proposal page

**Files:**
- Modify: `frontend/src/pages/proposals/builder.tsx`

- [ ] **Step 1: Locate the proposal page header / right place to mount**

Run: `cd frontend && grep -n "header\|ChatContainer\|proposalId" src/pages/proposals/builder.tsx | head -20`
Identify a sensible header location (where the proposal title or status sits).

- [ ] **Step 2: Wire `IdeateButton` and `IdeationDrawer`**

In `frontend/src/pages/proposals/builder.tsx`:

1. Add imports near the existing component imports:

```tsx
import { useState } from 'react'
import { IdeateButton } from '../../components/chat/ideate-button'
import { IdeationDrawer } from '../../components/chat/ideation-drawer'
```

2. Inside the page component, hold local state for the drawer and `proposalId` (which the page already has):

```tsx
const [ideateOpen, setIdeateOpen] = useState(false)
```

3. Render `<IdeateButton open={ideateOpen} onToggle={setIdeateOpen} />` in the proposal page header (or wherever the page renders nav-style controls).

4. Render `<IdeationDrawer open={ideateOpen} onClose={() => setIdeateOpen(false)} proposalId={proposalId} />` once at the page level (after the main layout JSX), so it overlays.

The exact placement should follow the existing layout conventions of `builder.tsx`. Don't restructure the page.

- [ ] **Step 3: Verify the page builds**

Run: `cd frontend && pnpm exec tsc -b 2>&1 | tail -10 && pnpm build 2>&1 | tail -10`
Expected: TypeScript: 0 errors; Vite build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/proposals/builder.tsx
git commit -m "feat(ui): mount IdeateButton and IdeationDrawer on the proposal page"
```

---

## Task 16: Full suites green + route count sanity check

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

- [ ] **Step 4: Route count**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print('routes:', len(app.routes))"`
Expected: `routes: 64` (62 before + 2 from Task 9).

- [ ] **Step 5: Commit (only if any fixes were needed)**

```bash
git add -A
git commit -m "test: fix fallout from ideation side-channel rollout"
```

---

## Task 17: Live smoke test against the docker stack

**Files:** none (manual verification).

- [ ] **Step 1: Rebuild and bring up the stack**

```bash
cd /Users/karthikramesh/Developer/nuprop
docker compose up --build -d
```

Wait for `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/v1/health` to return `200`.

- [ ] **Step 2: Apply the migration in the running Postgres**

The `app` service's command runs `alembic upgrade head` on every start. After the rebuild it should have applied `02_ideation_channel`. Verify:

```bash
docker compose exec db psql -U nuprop -d nuprop -c "\d chat_messages" | grep -E "channel|ix_chat_messages_proposal_channel_created"
```

Expected: `channel | character varying(20) | not null default 'main'`, and the new index in the index list.

- [ ] **Step 3: Open the proposal page and exercise the side-channel**

In a browser at `http://localhost:8080`, register / log in, create a proposal, then:

1. Click the **Ideate** button in the header. Drawer slides in from the right.
2. The empty state renders four clickable suggestions. Click one — text appears in the input.
3. Edit and send. Expect:
   - User message appears immediately in the drawer (channel: ideation).
   - "Typing…" indicator shows briefly.
   - Within ~5–10s the assistant message arrives via WS.
4. Refresh the page with `#ideate` in the URL — the drawer re-opens automatically.
5. Send a few more messages — observe that the proposal's main thread is untouched and `pipeline_state.current_phase` is unchanged.

```bash
# spot check from the API side
TOKEN=…  # JWT from login
PID=…    # proposal id

curl -s "http://localhost:8080/api/v1/chat/$PID/messages" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "http://localhost:8080/api/v1/chat/$PID/ideation/messages" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

The two endpoints return disjoint message lists.

- [ ] **Step 4: Verify the read-only invariant**

```bash
docker compose exec db psql -U nuprop -d nuprop -c "SELECT id, pipeline_state, brief FROM proposals ORDER BY created_at DESC LIMIT 1;"
```

After several ideation turns: `pipeline_state.current_phase` is still `"brief"` (or whatever it was), `brief` field is unchanged.

- [ ] **Step 5: Tear down**

```bash
cd /Users/karthikramesh/Developer/nuprop && docker compose down
```

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task(s) |
|---|---|
| Goals — read-only side-channel attached at any phase | Tasks 1, 5, 7, 8, 9, 13, 14, 15 |
| Non-goals (v2 list — multiple threads, apply-back, streaming, etc.) | Not implemented — covered by omission |
| Architecture — shared infra + new run_ideation phase | Tasks 5, 7 |
| Architecture — read-only invariant + structural class isolation | Task 5 (no `update` on `IdeationService`); Task 6 (test asserts) |
| Architecture — failure isolation (no pipeline_state mutation) | Task 7 (separate `_run_ideation_phase` shim, test asserts) |
| Data model — `channel` column + index + Alembic migration | Task 1 |
| Repository — `channel` filter | Task 2 |
| Pydantic — `ChatMessageResponse.channel` | Task 3 |
| Worker phase — `IdeationService.run_ideation` (cache_control, Tier.BALANCED, commit-before-broadcast) | Tasks 4 (prompt), 5 (run + cache test), 6 (failure propagation) |
| System prompt — empty-proposal handling + truncation cutoffs | Task 4 |
| API — `GET /chat/{id}/ideation/messages` + `POST /chat/{id}/ideation/send` | Task 9 |
| ViewModel additions | Task 8 |
| Frontend — `ChatMessage.channel`, store routing | Tasks 10, 11 |
| Frontend — API hooks | Task 12 |
| Frontend — Drawer (40%/560px desktop, full-screen mobile, dim overlay, empty state, error block) | Task 13 |
| Frontend — IdeateButton, URL hash sync | Task 14 |
| Frontend — page mounting | Task 15 |
| Tests — backend repo / service / worker / API | Tasks 2, 4, 5, 6, 7, 9 |
| Tests — frontend store / hooks / drawer / button | Tasks 11, 12, 13, 14 |
| Final smoke against docker | Task 17 |

**Placeholder scan:** No "TBD", "TODO", "later", "appropriate", "edge cases". The two places that say "follow the existing pattern" (Task 2 Step 4: `_coerce_id` import path, Task 15 Step 2: exact header location in `builder.tsx`) are precise instructions to follow named conventions in named files, not vague directives.

**Type / name consistency:**

- `channel` is the column / kwarg / payload field name everywhere — backend model, repo kwarg, Pydantic schema field, frontend `ChatMessage` field, store routing, drawer hydration.
- `run_ideation` is the consistent worker function name in `IdeationService`, in `app/workers/pipeline.py`, and in `ChatViewModel._enqueue` ("run_ideation" string).
- `Tier.BALANCED` resolves to `global.anthropic.claude-sonnet-4-6` via `AIService.model_for` (verified earlier in the session against `aws bedrock list-inference-profiles`).
- `_job_id` uses `{proposal_id}:run_ideation:{user_msg.id}` via the existing `_enqueue(..., idempotency_key=str(user_msg.id))` helper, matching the per-turn pattern landed in commit `15dfeef`.

**Scope check:** v1 surface is bounded — one column, two endpoints, one worker phase, one drawer, one button. v2 list is explicit in the spec and untouched here.
