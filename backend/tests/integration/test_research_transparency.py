"""End-to-end tests for the new run_research / run_benchmarks behaviour:
plan + activity log + annotated findings."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.pipeline_service import PipelineService


def _start(content_block):
    return SimpleNamespace(type="content_block_start", content_block=content_block)


def _delta(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _stop(content_block):
    return SimpleNamespace(type="content_block_stop", content_block=content_block)


class _MockStreamContext:
    """Stands in for the async context manager returned by messages.stream(...)."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self  # async-iterable below

    async def __aexit__(self, *a):
        return None

    def __aiter__(self):
        async def _gen():
            for ev in self._events:
                yield ev
        return _gen()


async def test_run_research_emits_plan_activity_log_and_findings(db, monkeypatch, make_proposal_db):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )

    # Mock the planner
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={
            "queries": ["Acme rebrand 2024", "Acme agency relationships"],
            "rationale": "Cover Acme's strategic context and who they already work with.",
        }),
    )

    # Mock the AI streaming call. Note: web-search citations don't include
    # offset fields; spans are computed by matching cited_text against the body.
    body_text = "Acme rebranded in 2024. Their previous identity was..."
    cited = "Acme rebranded in 2024."
    fake_events = [
        _start(SimpleNamespace(type="tool_use", name="web_search",
                                input={"query": "Acme rebrand 2024"})),
        _stop(SimpleNamespace(type="tool_use", name="web_search",
                               input={"query": "Acme rebrand 2024"})),
        _stop(SimpleNamespace(type="web_search_tool_result", content=[
            SimpleNamespace(url="https://example.com/a", title="Acme rebrand article"),
        ])),
        _delta(body_text),
        _stop(SimpleNamespace(
            type="text", text=body_text,
            citations=[SimpleNamespace(
                type="web_search_result_location",
                url="https://example.com/a", title="Acme rebrand article",
                cited_text=cited, encrypted_index="enc",
            )],
        )),
    ]
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext(fake_events))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    # Three messages should have landed on the main channel.
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
    assert "Acme rebranded in 2024." in findings.content
    assert findings.extra_data["phase"] == "research"
    assert len(findings.extra_data["citations"]) == 1
    assert findings.extra_data["citations"][0]["url"] == "https://example.com/a"
    assert findings.extra_data["citations"][0]["domain"] == "example.com"
    assert findings.extra_data["spans"]

    # proposal.research carries the plain markdown body (unchanged contract).
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert "Acme rebranded in 2024." in refetched.research


async def test_run_research_uses_opus_tier(monkeypatch, db, make_proposal_db):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    from app.services.llm import Tier
    mock_ai.model_for.assert_called_with(Tier.HEAVY)


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

    class _BrokenStream(_MockStreamContext):
        def __aiter__(self):
            async def _gen():
                raise RuntimeError("bedrock died")
                yield  # pragma: no cover
            return _gen()

    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_BrokenStream([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

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
    # proposal.research unchanged
    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(proposal.id)
    assert refetched.research is None


async def test_run_research_formats_system_prompt_with_no_remaining_placeholders(db, monkeypatch, make_proposal_db):
    """Regression: RESEARCH_SYSTEM is a str.format template with {client_name},
    {max_searches}, {context_section}, {template_section} placeholders. The
    worker must substitute them before sending to Bedrock — otherwise the model
    receives literal curly-brace text in its system prompt."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_research_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-opus-4-7")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_research(proposal.id)

    kwargs = mock_ai.client.messages.stream.call_args.kwargs
    system_arg = kwargs["system"]
    # Verify no leftover format placeholders. We check the specific placeholders
    # from RESEARCH_SYSTEM rather than just "{" — a system prompt may legitimately
    # contain a JSON example with braces.
    for placeholder in ("{client_name}", "{max_searches}", "{context_section}", "{template_section}"):
        assert placeholder not in system_arg, f"unformatted placeholder in system prompt: {placeholder}"


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

    body_text = "Typical India logo design rates: 50k-3 lakh."
    cited = "50k-3 lakh"
    fake_events = [
        _start(SimpleNamespace(type="tool_use", name="web_search",
                                input={"query": "logo design India rates 2024"})),
        _stop(SimpleNamespace(type="tool_use", name="web_search",
                               input={"query": "logo design India rates 2024"})),
        _stop(SimpleNamespace(type="web_search_tool_result", content=[
            SimpleNamespace(url="https://example.com/rates", title="India rate card"),
        ])),
        _delta(body_text),
        _stop(SimpleNamespace(
            type="text", text=body_text,
            citations=[SimpleNamespace(
                type="web_search_result_location",
                url="https://example.com/rates", title="India rate card",
                cited_text=cited, encrypted_index="enc",
            )],
        )),
    ]
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext(fake_events))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(proposal.id)
    types = [m.message_type for m in msgs]
    assert "benchmarks_plan" in types
    assert "benchmarks_activity_log" in types
    assert "benchmarks_findings" in types
    # The OLD combined "research_findings"-with-both-bodies emit is gone.
    findings_count = sum(1 for m in msgs if m.message_type == "research_findings")
    assert findings_count == 0  # this test only ran benchmarks, not research

    findings = next(m for m in msgs if m.message_type == "benchmarks_findings")
    assert findings.extra_data["phase"] == "benchmarks"
    assert "50k-3 lakh" in findings.content


async def test_run_benchmarks_uses_balanced_sonnet_tier(monkeypatch, db, make_proposal_db):
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    from app.services.llm import Tier
    mock_ai.model_for.assert_called_with(Tier.BALANCED)


async def test_run_benchmarks_formats_system_prompt_with_no_remaining_placeholders(db, monkeypatch, make_proposal_db):
    """Regression: BENCHMARK_SYSTEM is a str.format template with
    {max_searches} and {categories_section} placeholders. The worker must
    substitute them before sending to Bedrock."""
    _, _, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": [{"category": "Logo"}]}},
        pipeline_state={"current_phase": "research", "phases_completed": []},
    )
    monkeypatch.setattr(
        "app.services.pipeline_service.generate_benchmarks_plan",
        AsyncMock(return_value={"queries": [], "rationale": ""}),
    )
    mock_ai = MagicMock()
    mock_ai.client.messages.stream = MagicMock(return_value=_MockStreamContext([]))
    mock_ai.model_for = MagicMock(return_value="global.anthropic.claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline_service.get_ai_service", lambda: mock_ai)

    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    kwargs = mock_ai.client.messages.stream.call_args.kwargs
    system_arg = kwargs["system"]
    for placeholder in ("{max_searches}", "{categories_section}"):
        assert placeholder not in system_arg, f"unformatted placeholder in system prompt: {placeholder}"
    # The categories section should mention "Logo" (the deliverable category).
    assert "Logo" in system_arg
