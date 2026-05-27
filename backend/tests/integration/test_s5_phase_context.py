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
        return {"queries": [], "rationale": ""}

    monkeypatch.setattr(ps, "generate_benchmarks_plan", fake_plan)

    # synthesize_research is the new seam (was streaming + tool-use). It
    # receives the user_message kwarg directly — capture it for the assertion.
    async def fake_synth(*, queries, system_prompt, user_message, on_event, **_):
        captured["user_message"] = user_message
        return "benchmark body", [], []

    monkeypatch.setattr(ps, "synthesize_research", fake_synth)

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.run_benchmarks(proposal.id)

    assert "ACME CONTEXT BRIEF" in captured["user_message"]


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
async def test_generate_sections_passes_context_brief(make_proposal_db, db, monkeypatch):
    """generate_sections threads context_brief into each section generator call."""
    agency, client, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
    await ProposalRepository(db).update(
        proposal.id, context_brief="ACME CONTEXT BRIEF", cost_model={"line_items": []},
    )
    await db.commit()

    captured_context_briefs: list[str | None] = []

    async def fake_fact(section_type, context_brief=None, **_):
        captured_context_briefs.append(context_brief)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    async def fake_synth(section_type, context_brief=None, **_):
        captured_context_briefs.append(context_brief)
        return {"content": "x", "assets": [], "included": True, "metadata": {}}

    from app.services.ai import section_facts, section_synthesis
    import app.services.pipeline_service as ps
    monkeypatch.setattr(section_facts, "generate_fact_section", fake_fact)
    monkeypatch.setattr(section_synthesis, "generate_synthesis_section", fake_synth)
    monkeypatch.setattr(ps, "generate_fact_section", fake_fact)
    monkeypatch.setattr(ps, "generate_synthesis_section", fake_synth)

    from app.services.pipeline_service import PipelineService
    from unittest.mock import AsyncMock
    svc = PipelineService(db, AsyncMock())
    await svc.generate_sections(proposal.id)

    assert any(cb == "ACME CONTEXT BRIEF" for cb in captured_context_briefs), (
        f"context_brief was not passed to any section generator; got: {captured_context_briefs}"
    )
