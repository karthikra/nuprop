"""Integration tests for PipelineService — each phase against a real session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


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


async def test_analyze_brief_persists_completed_brief_before_emitting(db, monkeypatch, make_proposal_db):
    from app.services.ai.brief_analyzer import BriefAnalysisResult, BriefAnalyzer

    _, _, proposal = await make_proposal_db()
    pid = proposal.id

    async def fake_analyze(self, chat_history, current_brief, context_brief=None):
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


async def test_build_cost_model_commits_model_and_creates_message(db, make_proposal_db):
    from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository

    agency, _, proposal = await make_proposal_db(
        brief={"project": {"deliverables": [{"category": "logo design", "details": "mark", "quantity": 1}]}}
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


async def test_generate_sections_populates_columns_and_advances_pipeline(db, monkeypatch, make_proposal_db):
    """generate_sections writes section payloads to each column and advances
    pipeline_state to section_editor."""
    from app.services.ai import section_facts, section_synthesis
    import app.services.pipeline_service as ps

    agency, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "section_generation", "phases_completed": ["research"]},
    )
    pid = proposal.id

    async def _fake_fact(section_type, **_):
        return {"content": f"FACT {section_type}", "assets": [], "included": True, "metadata": {}}

    async def _fake_synth(section_type, **_):
        return {"content": f"SYNTH {section_type}", "assets": [], "included": True, "metadata": {}}

    monkeypatch.setattr(section_facts, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", _fake_synth)
    monkeypatch.setattr(ps, "generate_fact_section", _fake_fact)
    monkeypatch.setattr(ps, "generate_synthesis_section", _fake_synth)

    svc = PipelineService(db, AsyncMock())
    await svc.generate_sections(pid)

    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        # executive_summary is a synthesis section — content should be populated
        assert refetched.executive_summary is not None
        assert refetched.executive_summary["content"] == "SYNTH executive_summary"
        assert refetched.pipeline_state["current_phase"] == "section_editor"
