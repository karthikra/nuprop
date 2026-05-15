"""Unit tests for the Redis pub/sub WebSocket bridge."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.queue import events

WS_CHANNEL = "nuprop:ws"


async def test_publish_pushes_a_json_envelope_to_the_channel():
    redis = AsyncMock()
    await events.publish(redis, "prop-1", {"type": "phase_change", "phase": "research"})
    redis.publish.assert_awaited_once()
    channel, raw = redis.publish.await_args.args
    assert channel == WS_CHANNEL
    envelope = json.loads(raw)
    assert envelope == {
        "proposal_id": "prop-1",
        "payload": {"type": "phase_change", "phase": "research"},
    }


async def test_handle_event_relays_to_ws_manager(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(events.ws_manager, "broadcast", broadcast)
    raw = json.dumps({"proposal_id": "prop-9", "payload": {"type": "typing", "typing": True}})
    await events._handle_event(raw)
    broadcast.assert_awaited_once_with("prop-9", {"type": "typing", "typing": True})


async def test_handle_event_ignores_malformed_payloads(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(events.ws_manager, "broadcast", broadcast)
    await events._handle_event("not-json{")  # must not raise
    broadcast.assert_not_awaited()
