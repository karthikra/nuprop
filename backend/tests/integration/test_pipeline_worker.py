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
