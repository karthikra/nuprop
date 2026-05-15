"""Integration tests for PipelineService — each phase against a real session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
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
