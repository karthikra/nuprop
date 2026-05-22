from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_analyze_brief_passes_context_brief(make_proposal_db, db, monkeypatch):
    """analyze_brief threads context_brief into BriefAnalyzer.analyze."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})

    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    captured = {}

    async def fake_analyze(self, chat_history, current_brief, context_brief=None):
        captured["context_brief"] = context_brief
        from app.services.ai.brief_analyzer import BriefAnalysisResult
        return BriefAnalysisResult(
            response_text="ok", brief_complete=False, brief_data={},
        )

    monkeypatch.setattr("app.services.ai.brief_analyzer.BriefAnalyzer.analyze", fake_analyze)

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.analyze_brief(proposal.id)

    assert captured["context_brief"] == "ACME CONTEXT BRIEF"


@pytest.mark.asyncio
async def test_run_benchmarks_injects_context_into_user_message(
    make_proposal_db, db, monkeypatch,
):
    """run_benchmarks appends the context brief to the benchmark user message."""
    agency, client, proposal = await make_proposal_db(
        brief={"client": {"name": "Acme"}, "project": {"deliverables": []}},
    )
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    captured = {}
    import app.services.pipeline_service as ps

    async def fake_plan(brief):
        return {"searches": []}

    monkeypatch.setattr(ps, "generate_benchmarks_plan", fake_plan)

    class _FakeStream:
        def __init__(self, messages): captured["messages"] = messages
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _FakeMessages:
        def stream(self, **kwargs):
            return _FakeStream(kwargs.get("messages"))

    class _FakeClient:
        messages = _FakeMessages()

    class _FakeAI:
        client = _FakeClient()
        def model_for(self, tier): return "fake-model"

    monkeypatch.setattr(ps, "get_ai_service", lambda: _FakeAI())

    async def fake_process_stream(stream, on_event=None):
        return ("benchmark body", [], [])

    monkeypatch.setattr(ps, "process_stream", fake_process_stream)

    # Patch ActivityFlusher so flush() doesn't error against the fake stream
    from app.services.research_streaming import ActivityFlusher
    monkeypatch.setattr(ActivityFlusher, "flush", lambda *a, **kw: _async_noop())

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    user_msg = captured["messages"][0]["content"]
    assert "ACME CONTEXT BRIEF" in user_msg


async def _async_noop(*a, **kw):
    return None


@pytest.mark.asyncio
async def test_run_ideation_includes_context_brief_in_system_prompt(
    make_proposal_db, db, monkeypatch,
):
    """run_ideation puts the context brief into the ideation system prompt."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(proposal.id, context_brief="ACME CONTEXT BRIEF")
    await db.commit()

    # Seed one user message on the ideation channel so run_ideation has input.
    from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
    from app.infrastructure.db.models.chat_message import MessageRole, MessageType
    await ChatMessageRepository(db).create(
        proposal_id=proposal.id, role=MessageRole.USER.value,
        message_type=MessageType.TEXT.value, content="What's the angle?",
        phase="ideation", channel="ideation",
    )
    await db.commit()

    captured = {}

    async def fake_messages_create(self, **kwargs):
        captured["system"] = kwargs.get("system")
        class _Resp:
            content = [type("B", (), {"text": "an idea"})()]
        return _Resp()

    monkeypatch.setattr(
        "app.services.llm.AIService.messages_create", fake_messages_create
    )

    from app.services.ideation_service import IdeationService
    from unittest.mock import AsyncMock
    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(proposal.id)

    system = captured["system"]
    text = " ".join(block["text"] for block in system) if isinstance(system, list) else str(system)
    assert "ACME CONTEXT BRIEF" in text


@pytest.mark.asyncio
async def test_generate_narrative_passes_context_brief(make_proposal_db, db, monkeypatch):
    """generate_narrative threads context_brief into NarrativeGenerator.generate_all."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(
        proposal.id, context_brief="ACME CONTEXT BRIEF", cost_model={"line_items": []},
    )
    await db.commit()

    captured = {}

    async def fake_generate_all(self, **kwargs):
        captured.update(kwargs)
        from app.services.ai.narrative_generator import NarrativeResult
        return NarrativeResult(
            covering_letter="", covering_letter_alt="",
            letter_strategy_primary="confident", letter_strategy_alt="warm",
            executive_summary="",
            scope_sections=[], cost_rationale="", terms="",
        )

    monkeypatch.setattr(
        "app.services.ai.narrative_generator.NarrativeGenerator.generate_all", fake_generate_all
    )

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.generate_narrative(proposal.id)

    assert captured.get("context_brief") == "ACME CONTEXT BRIEF"
