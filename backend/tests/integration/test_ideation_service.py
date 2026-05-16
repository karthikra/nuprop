"""Integration tests for IdeationService.run_ideation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.db.database import async_session_factory
from app.infrastructure.db.models.chat_message import MessageRole
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.ideation_service import IdeationService


async def _make_proposal(db, *, brief=None):
    agency = await AgencyRepository(db).create(name="ID Agency", slug="id-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="Ideation Project",
        brief=brief or {},
        pipeline_state={"current_phase": "brief", "phases_completed": []},
    )
    await db.commit()
    return agency, client, proposal


def _bedrock_reply(text: str):
    """Build the minimal anthropic-SDK response shape IdeationService consumes."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


async def test_run_ideation_persists_assistant_msg_on_ideation_channel(db, monkeypatch):
    _, _, proposal = await _make_proposal(db)
    pid = proposal.id

    # Seed a user message on the ideation channel so the service has chat history to send.
    msg_repo = ChatMessageRepository(db)
    await msg_repo.create(
        proposal_id=pid, role=MessageRole.USER.value, message_type="text",
        content="What angle should we lead with?", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(return_value=_bedrock_reply("Try angle X because Y."))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(pid)

    # The assistant reply is in the DB on the ideation channel, committed.
    async with async_session_factory() as fresh:
        msgs = await ChatMessageRepository(fresh).list_by_proposal(pid, channel="ideation")
        roles_and_content = [(m.role, m.content) for m in msgs]
        assert ("assistant", "Try angle X because Y.") in roles_and_content
        # User message is still there.
        assert any(r == "user" and c.startswith("What angle") for r, c in roles_and_content)

    # The main channel was not touched.
    async with async_session_factory() as fresh:
        main = await ChatMessageRepository(fresh).list_by_proposal(pid)
        assert main == []  # default channel is "main"; the ideation msgs don't leak in


async def test_run_ideation_passes_cache_control_system_block_to_bedrock(db, monkeypatch):
    _, _, proposal = await _make_proposal(db, brief={"client": {"name": "Acme"}})
    await ChatMessageRepository(db).create(
        proposal_id=proposal.id, role="user", message_type="text",
        content="ping", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(return_value=_bedrock_reply("pong"))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    svc = IdeationService(db, AsyncMock())
    await svc.run_ideation(proposal.id)

    kwargs = fake_create.await_args.kwargs
    # System block is a list (not a bare string) and carries cache_control.
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Cached prompt mentions the read-only invariant + the project name.
    assert "ideation copilot" in kwargs["system"][0]["text"]
    assert "Ideation Project" in kwargs["system"][0]["text"]
    # Messages are the ideation channel history, not the (empty) main one.
    assert kwargs["messages"] == [{"role": "user", "content": "ping"}]


async def test_run_ideation_does_not_mutate_proposal_fields(db, monkeypatch):
    """The read-only invariant: nothing on ``proposal.*`` changes."""
    _, _, proposal = await _make_proposal(db, brief={"client": {"name": "Acme"}})
    pid = proposal.id
    await ChatMessageRepository(db).create(
        proposal_id=pid, role="user", message_type="text",
        content="hi", phase="ideation", channel="ideation",
    )
    await db.commit()

    before = (proposal.brief, proposal.research, proposal.cost_model,
              proposal.covering_letter, proposal.pipeline_state)

    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(AsyncMock(return_value=_bedrock_reply("ok"))),
    )

    await IdeationService(db, AsyncMock()).run_ideation(pid)

    async with async_session_factory() as fresh:
        refetched = await ProposalRepository(fresh).get_by_id(pid)
        after = (refetched.brief, refetched.research, refetched.cost_model,
                 refetched.covering_letter, refetched.pipeline_state)
    assert before == after, "ideation must not mutate proposal fields"


async def test_run_ideation_commits_before_broadcasting(db, monkeypatch):
    """Spy on publish — confirm the assistant row is already visible from a
    fresh session at the moment publish is awaited. Locks in the
    commit-before-broadcast invariant that the whole worker rewrite hinged on.
    """
    _, _, proposal = await _make_proposal(db)
    pid = proposal.id
    await ChatMessageRepository(db).create(
        proposal_id=pid, role="user", message_type="text",
        content="hi", phase="ideation", channel="ideation",
    )
    await db.commit()

    row_visible_at_publish_time: list[bool] = []

    async def _spy_publish(redis, proposal_id, payload):
        async with async_session_factory() as fresh:
            msgs = await ChatMessageRepository(fresh).list_by_proposal(
                str(proposal_id), channel="ideation",
            )
            row_visible_at_publish_time.append(
                any(m.role == "assistant" for m in msgs)
            )

    monkeypatch.setattr("app.services.ideation_service.publish", _spy_publish)
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(AsyncMock(return_value=_bedrock_reply("ok"))),
    )

    await IdeationService(db, AsyncMock()).run_ideation(pid)

    assert row_visible_at_publish_time == [True], (
        "assistant row must be committed BEFORE publish is called"
    )


async def test_run_ideation_sends_only_ideation_history_to_bedrock(db, monkeypatch):
    """Main-channel messages must NOT bleed into the ideation context."""
    _, _, proposal = await _make_proposal(db)
    pid = proposal.id

    msg_repo = ChatMessageRepository(db)
    await msg_repo.create(
        proposal_id=pid, role="user", message_type="text",
        content="MAIN CHANNEL — DO NOT SEND", phase="brief", channel="main",
    )
    await msg_repo.create(
        proposal_id=pid, role="user", message_type="text",
        content="ideation question", phase="ideation", channel="ideation",
    )
    await db.commit()

    fake_create = AsyncMock(return_value=_bedrock_reply("ok"))
    monkeypatch.setattr(
        "app.services.ideation_service.get_ai_service",
        lambda: _StubAI(fake_create),
    )

    await IdeationService(db, AsyncMock()).run_ideation(pid)

    sent = fake_create.await_args.kwargs["messages"]
    contents = [m["content"] for m in sent]
    assert "ideation question" in contents
    assert all("MAIN CHANNEL" not in c for c in contents), (
        f"main-channel msgs leaked into ideation prompt: {contents}"
    )


class _StubAI:
    """Bare-bones stand-in for AIService used by run_ideation."""

    def __init__(self, messages_create):
        self.messages_create = messages_create

    def model_for(self, tier):
        return "global.anthropic.claude-sonnet-4-6"
