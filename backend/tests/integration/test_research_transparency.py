"""End-to-end tests for run_research / run_benchmarks: plan + activity log + findings.

The Anthropic-hosted ``web_search_20250305`` tool isn't available on AWS Bedrock
in ap-northeast-1 (see HANDOFF § 5e + bedrock-web-search-fix.md). The pipeline
now routes through ``web_search_loop.synthesize_research`` which runs Serper-backed
searches and synthesizes via a single non-streaming Sonnet 4.6 call.

These tests monkeypatch ``synthesize_research`` at its import point in
``pipeline_service`` — the cleanest seam now that the streaming/tool-use shape
is gone. Each test verifies a different slice of the contract.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


def _make_synthesize_mock(
    *,
    body: str = "stub body",
    citations: list[dict] | None = None,
    spans: list[dict] | None = None,
    raises: Exception | None = None,
    emit_events: list[dict] | None = None,
):
    """Build an AsyncMock for synthesize_research that captures call kwargs,
    emits a few activity events via on_event (so the activity_log message
    gets a non-empty events array), then returns the canned response."""
    captured: dict[str, Any] = {}

    async def _impl(*, queries, system_prompt, user_message, on_event, **rest):
        captured["queries"] = queries
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        captured["rest"] = rest
        # Emit something so the flusher has events to persist + the test
        # can assert that the activity log path runs end-to-end.
        events = emit_events if emit_events is not None else [
            {"type": "search", "query": "stub", "ts": "2026-01-01T00:00:00+00:00"},
            {"type": "read", "url": "https://example.com/a", "title": "A", "ts": "2026-01-01T00:00:00+00:00"},
            {"type": "note", "text": "synth", "ts": "2026-01-01T00:00:00+00:00"},
        ]
        for e in events:
            await on_event(e)
        if raises is not None:
            raise raises
        return body, citations or [], spans or []

    mock = AsyncMock(side_effect=_impl)
    return mock, captured


async def test_run_research_emits_plan_activity_log_and_findings(db, monkeypatch, make_proposal_db):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={
            "queries": ["Acme rebrand 2024", "Acme agency relationships"],
            "rationale": "Cover Acme's strategic context.",
        }),
    )
    body_text = "Acme rebranded in 2024 [1]. Their previous identity was..."
    citations = [
        {"id": 1, "url": "https://example.com/a", "title": "Acme rebrand article",
         "domain": "example.com", "cited_text": ""},
    ]
    mock_syn, _captured = _make_synthesize_mock(body=body_text, citations=citations)
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "research_plan" in types
    assert "research_activity_log" in types
    assert "research_findings" in types

    plan = next(m for m in msgs if m.message_type == "research_plan")
    assert plan.extra_data["queries"] == ["Acme rebrand 2024", "Acme agency relationships"]
    assert plan.extra_data["phase"] == "research"

    log = next(m for m in msgs if m.message_type == "research_activity_log")
    assert log.extra_data["status"] == "complete"
    event_types = [e["type"] for e in log.extra_data["events"]]
    assert "search" in event_types
    assert "read" in event_types

    findings = next(m for m in msgs if m.message_type == "research_findings")
    assert "Acme rebranded in 2024" in findings.content
    assert findings.extra_data["phase"] == "research"
    assert len(findings.extra_data["citations"]) == 1
    assert findings.extra_data["citations"][0]["url"] == "https://example.com/a"
    assert findings.extra_data["citations"][0]["domain"] == "example.com"
    # spans intentionally empty under the Serper path — see web_search_loop docstring.
    assert findings.extra_data["spans"] == []

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert "Acme rebranded in 2024" in refetched.research


async def test_run_research_passes_planner_queries_to_synthesizer(
    db, monkeypatch, make_proposal_db,
):
    """The planner's queries must reach synthesize_research verbatim — it's
    the contract between the two stages."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": ["q1", "q2", "q3"], "rationale": "..."}),
    )
    mock_syn, captured = _make_synthesize_mock()
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    assert captured["queries"] == ["q1", "q2", "q3"]


async def test_run_research_failure_marks_activity_log_failed_and_does_not_create_findings(
    db, monkeypatch, make_proposal_db,
):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_syn, _ = _make_synthesize_mock(raises=RuntimeError("bedrock died"))
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    with pytest.raises(RuntimeError, match="bedrock died"):
        await svc.run_research(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "research_activity_log" in types
    log = next(m for m in msgs if m.message_type == "research_activity_log")
    assert log.extra_data["status"] == "failed"
    assert "bedrock died" in (log.extra_data.get("error") or "")
    assert "research_findings" not in types

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert refetched.research is None


async def test_run_research_formats_system_prompt_with_no_remaining_placeholders(
    db, monkeypatch, make_proposal_db,
):
    """Regression: RESEARCH_SYSTEM is a str.format template with {client_name},
    {max_searches}, {context_section}, {template_section}. The worker must
    substitute them before passing the prompt downstream."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_syn, captured = _make_synthesize_mock()
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    system_prompt = captured["system_prompt"]
    for placeholder in ("{client_name}", "{max_searches}", "{context_section}", "{template_section}"):
        assert placeholder not in system_prompt, f"unformatted placeholder: {placeholder}"


async def test_run_benchmarks_emits_separate_findings_message_with_benchmarks_phase(
    db, monkeypatch, make_proposal_db,
):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": [{"category": "Logo"}]}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={
            "queries": ["logo design India rates 2024"],
            "rationale": "Find India-specific rate ranges.",
        }),
    )
    body_text = "Typical India logo design rates: 50k-3 lakh [1]."
    citations = [
        {"id": 1, "url": "https://example.com/rates", "title": "India rate card",
         "domain": "example.com", "cited_text": ""},
    ]
    mock_syn, _ = _make_synthesize_mock(body=body_text, citations=citations)
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "benchmarks_plan" in types
    assert "benchmarks_activity_log" in types
    assert "benchmarks_findings" in types
    # Benchmarks doesn't write to the research_findings type.
    assert sum(1 for m in msgs if m.message_type == "research_findings") == 0

    findings = next(m for m in msgs if m.message_type == "benchmarks_findings")
    assert findings.extra_data["phase"] == "benchmarks"
    assert "50k-3 lakh" in findings.content


async def test_run_benchmarks_formats_system_prompt_with_no_remaining_placeholders(
    db, monkeypatch, make_proposal_db,
):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": [{"category": "Logo"}]}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_syn, captured = _make_synthesize_mock()
    monkeypatch.setattr("app.services.pipeline_service.synthesize_research", mock_syn)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    system_prompt = captured["system_prompt"]
    for placeholder in ("{max_searches}", "{categories_section}"):
        assert placeholder not in system_prompt, f"unformatted placeholder: {placeholder}"
    assert "Logo" in system_prompt
