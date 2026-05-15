"""Tests for ActivityFlusher batched-flush behaviour."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.research_streaming import (
    _FLUSH_MAX_EVENTS,
    _FLUSH_MAX_INTERVAL_S,
    ActivityFlusher,
)


async def _make_log_message(db, *, phase="research"):
    agency = await AgencyRepository(db).create(name="RS Agency", slug="rs-agency")
    client = await ClientRepository(db).create(agency_id=agency.id, name="C", slug="c")
    proposal = await ProposalRepository(db).create(
        agency_id=agency.id, client_id=client.id, project_name="RS Project",
        brief={}, pipeline_state={"current_phase": "research"},
    )
    msg_repo = ChatMessageRepository(db)
    msg = await msg_repo.create(
        proposal_id=proposal.id,
        role="assistant",
        message_type=f"{phase}_activity_log",
        content="",
        extra_data={"phase": phase, "status": "running", "events": []},
        phase=phase,
    )
    await db.commit()
    return proposal, msg, msg_repo


async def test_flush_triggers_when_event_count_threshold_hit(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    # Append _FLUSH_MAX_EVENTS events — should fire exactly one flush.
    for i in range(_FLUSH_MAX_EVENTS):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    assert redis.publish.await_count == 1


async def test_flush_does_not_trigger_under_threshold_and_within_interval(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    # Append fewer than the threshold; no flush should fire.
    for i in range(_FLUSH_MAX_EVENTS - 1):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    assert redis.publish.await_count == 0


async def test_explicit_flush_with_final_status_marks_completion(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    await flusher.append({"type": "search", "query": "q1", "ts": "t"})
    await flusher.flush(final_status="complete")
    # Re-read the message to assert the persisted state.
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ChatMessageRepository(fresh).get_by_id(log_msg.id)
    assert refetched.extra_data["status"] == "complete"
    assert len(refetched.extra_data["events"]) == 1


async def test_flush_failed_status_records_error(db):
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    await flusher.flush(final_status="failed", error="bedrock died")
    from app.infrastructure.db.database import async_session_factory
    async with async_session_factory() as fresh:
        refetched = await ChatMessageRepository(fresh).get_by_id(log_msg.id)
    assert refetched.extra_data["status"] == "failed"
    assert refetched.extra_data["error"] == "bedrock died"


async def test_flush_publishes_message_updated_event(db):
    """The published WS payload must be a message_updated event (not new_message)."""
    proposal, log_msg, msg_repo = await _make_log_message(db)
    redis = AsyncMock()
    flusher = ActivityFlusher(
        session=db, msg_repo=msg_repo, redis=redis,
        log_msg_id=log_msg.id, proposal_id=proposal.id, phase="research",
    )
    for i in range(_FLUSH_MAX_EVENTS):
        await flusher.append({"type": "search", "query": f"q{i}", "ts": "t"})
    redis.publish.assert_awaited()
    _, raw = redis.publish.await_args.args
    import json as _json
    envelope = _json.loads(raw)
    assert envelope["payload"]["type"] == "message_updated"
    assert envelope["payload"]["message"]["message_type"] == "research_activity_log"
