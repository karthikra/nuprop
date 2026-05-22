from __future__ import annotations

import pytest

from app.services.context_service import get_or_create_proposal_brief


@pytest.mark.asyncio
async def test_generates_persists_and_reuses(make_proposal_db, db, monkeypatch):
    """First call generates + persists; second call reads the column, no regen."""
    agency, client, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}},
    )
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

    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    repo = ProposalRepository(db)
    p1 = await repo.get_by_id(proposal.id)

    brief1 = await get_or_create_proposal_brief(db, p1)
    assert brief1 == "BRIEF for Acme"
    assert calls["n"] == 1

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
