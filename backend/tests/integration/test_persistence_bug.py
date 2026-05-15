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

    # Record every emit with whether the committed write was visible at that point.
    # The invariant is: any "complete" / state-change broadcast must follow the
    # phase commit (the bug was that they did not). A "searching" progress event
    # legitimately fires *before* the write — it's a "starting work" signal.
    observations: list[tuple[dict, bool]] = []

    async def _emit_spy(redis, proposal_id, payload):  # noqa: ANN001
        async with async_session_factory() as observer:
            row = await ProposalRepository(observer).get_by_id(proposal_id)
            committed = row is not None and row.research == research_text
            observations.append((payload, committed))

    monkeypatch.setattr("app.services.pipeline_service.publish", _emit_spy, raising=False)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(pid)

    assert observations, "run_research should emit at least one WS event"
    # The phase-completion broadcast must see the committed write.
    completion_emits = [
        committed for payload, committed in observations
        if payload.get("status") == "complete"
    ]
    assert completion_emits, "expected a 'complete' progress broadcast from run_research"
    assert all(completion_emits), "every phase-completion broadcast must follow the phase commit"
