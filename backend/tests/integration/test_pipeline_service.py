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


_merge = PipelineService._merge_preferences_into_config


def test_merge_no_config_and_no_prefs_is_empty():
    assert _merge(None, {}) == {}


def test_merge_empty_prefs_returns_a_copy_of_config():
    config = {"narrative": {"letter_strategy": "vision"}}
    merged = _merge(config, {})
    assert merged == config
    assert merged is not config  # a copy, not the same object


def test_merge_prefs_override_and_extend_narrative_section():
    config = {"narrative": {"letter_strategy": "vision", "scope_detail_level": "high"}}
    merged = _merge(config, {"letter_strategy": "warm", "letter_length": "short"})
    assert merged["narrative"]["letter_strategy"] == "warm"      # overridden
    assert merged["narrative"]["letter_length"] == "short"       # added
    assert merged["narrative"]["scope_detail_level"] == "high"   # untouched


def test_merge_prefs_populate_cost_model_and_output_sections():
    merged = _merge(
        {},
        {"pricing_model": "tiered", "discount_tags": ["existing_client"], "site_theme": "dark"},
    )
    assert merged["cost_model"]["pricing_model"] == "tiered"
    assert merged["cost_model"]["default_multipliers"] == ["existing_client"]
    assert merged["output"]["site_theme"] == "dark"


def test_merge_does_not_mutate_the_input_config():
    config = {"narrative": {"letter_strategy": "vision"}}
    _merge(config, {"letter_strategy": "warm"})
    assert config["narrative"]["letter_strategy"] == "vision"


def test_merge_preferences_into_config_overlays_user_prefs():
    merged = _merge(
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


async def test_generate_outputs_commits_status_and_advances_to_complete(db, tmp_path, monkeypatch):
    # OUTPUT_DIR is a @computed_field — patch get_settings() in the pipeline module
    # to return a stub whose OUTPUT_DIR points at tmp_path so generated files land there.
    from app.core.config import get_settings as real_get_settings

    real_settings = real_get_settings()

    class _StubSettings:
        OUTPUT_DIR = str(tmp_path)

        def __getattr__(self, name):  # delegate everything else to the real settings
            return getattr(real_settings, name)

    monkeypatch.setattr(
        "app.services.pipeline_service.get_settings", lambda: _StubSettings()
    )

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
