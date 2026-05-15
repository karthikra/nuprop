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


from types import SimpleNamespace

from app.services.research_streaming import process_stream


def _start(content_block):
    return SimpleNamespace(type="content_block_start", content_block=content_block)


def _delta(text):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _stop(content_block):
    return SimpleNamespace(type="content_block_stop", content_block=content_block)


def _tool_use(query):
    return SimpleNamespace(type="tool_use", name="web_search", input={"query": query})


def _ws_result(*results):
    return SimpleNamespace(type="web_search_tool_result", content=list(results))


def _ws_result_item(url, title):
    return SimpleNamespace(url=url, title=title)


def _text_block(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations or [])


def _citation(url, title, cited_text, start, end):
    return SimpleNamespace(
        url=url, title=title, cited_text=cited_text,
        start_block_index=start, end_block_index=end,
    )


class _AsyncIter:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        async def _gen():
            for item in self._items:
                yield item
        return _gen()


async def test_process_stream_records_search_events():
    events: list[dict] = []
    stream = _AsyncIter([
        _start(_tool_use("Pepsi Global revenue")),
        _stop(_tool_use("Pepsi Global revenue")),
    ])
    body, citations, spans = await process_stream(stream, on_event=events.append)
    search_events = [e for e in events if e["type"] == "search"]
    assert search_events == [{"type": "search", "query": "Pepsi Global revenue", "ts": search_events[0]["ts"]}]


async def test_process_stream_records_read_events_for_each_result_url():
    events: list[dict] = []
    stream = _AsyncIter([
        _start(_ws_result(
            _ws_result_item("https://reuters.com/a", "Pepsi Q4"),
            _ws_result_item("https://ft.com/b", "Beverage growth"),
        )),
    ])
    await process_stream(stream, on_event=events.append)
    reads = [e for e in events if e["type"] == "read"]
    assert len(reads) == 2
    assert reads[0]["url"] == "https://reuters.com/a"
    assert reads[0]["title"] == "Pepsi Q4"
    assert reads[1]["url"] == "https://ft.com/b"


async def test_process_stream_accumulates_body_from_text_deltas():
    events: list[dict] = []
    stream = _AsyncIter([
        _delta("Pepsi Global "),
        _delta("revenue grew 8.2% YoY."),
    ])
    body, _, _ = await process_stream(stream, on_event=events.append)
    assert body == "Pepsi Global revenue grew 8.2% YoY."


async def test_process_stream_collects_citations_from_text_block_stop():
    events: list[dict] = []
    citation = _citation("https://reuters.com/a", "Pepsi Q4", "Revenue grew 8.2% YoY.", 0, 31)
    stream = _AsyncIter([
        _delta("Pepsi Global revenue grew 8.2%."),
        _stop(_text_block("Pepsi Global revenue grew 8.2%.", citations=[citation])),
    ])
    _, citations, spans = await process_stream(stream, on_event=events.append)
    assert len(citations) == 1
    assert citations[0]["url"] == "https://reuters.com/a"
    assert citations[0]["domain"] == "reuters.com"
    assert citations[0]["id"] == 1
    assert spans == [{"start": 0, "end": 31, "citation_ids": [1]}]


async def test_process_stream_dedupes_citations_by_url():
    """Two citations for the same URL = one entry in citations, two spans."""
    cit1 = _citation("https://reuters.com/a", "Pepsi Q4", "Snippet A", 0, 20)
    cit2 = _citation("https://reuters.com/a", "Pepsi Q4", "Snippet B", 50, 70)
    events: list[dict] = []
    stream = _AsyncIter([
        _stop(_text_block("...", citations=[cit1, cit2])),
    ])
    _, citations, spans = await process_stream(stream, on_event=events.append)
    assert len(citations) == 1
    assert len(spans) == 2
    assert all(s["citation_ids"] == [1] for s in spans)


async def test_process_stream_emits_synthesizing_note_at_end():
    """After the stream ends the worker is doing final synthesis — surface that."""
    events: list[dict] = []
    stream = _AsyncIter([])
    await process_stream(stream, on_event=events.append)
    notes = [e for e in events if e["type"] == "note"]
    assert notes and "Synthesizing" in notes[0]["text"]
